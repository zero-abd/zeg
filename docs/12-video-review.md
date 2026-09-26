# Video review: face and gaze flags with Haar cascades

zeg's screen is audio first. A candidate may also send their camera, and when they do,
`zeg-gaze` (services/vision) watches it and marks spans of the call for a person to
look at: the candidate looking away from the screen for more than five seconds, no face
in view, or more than one face in view. The marks go into the report under "Video
review", with timestamps, and nowhere else. They do not touch the score.

This document explains how the detector works from the pixels up, how well it does on
labelled clips, and where it fails. It is written to be learned from, so it spends
time on the classical computer vision underneath.

## Where it sits

```
candidate browser ── WebRTC video, 640x480 at 15 fps (optional) ──► gateway
    webrtc.consume_video ──video_sink──► GazeReview.sink       (event loop, never blocks)
        └─ worker thread: PyAV scale + BGR ──► zeg_gaze.Session.push_bgr   (C++, pybind11)
               Detector ─► classify ─► median + majority smoothing ─► Segmenter
hangup ──► GazeReview.finish() ──► flags ──► report "Video review" (zeg/video_review.py)

after the call:  zeg-gaze call.mp4 --out flags.json  ──►  zeg.cli --video-flags flags.json
```

The detector is C++ because it runs on every frame of every call, and because OpenCV's
cascade code is C++ anyway. Python sees one call per frame through a pybind11 module
that releases the GIL while the frame is analysed. The gateway hands frames to a worker
thread through a two-slot queue: when the detector falls behind, new frames are
dropped, not queued, because a flag needs seconds of evidence and a backlog only adds
lag to the audio path that shares the process.

## 1. Finding a face: Viola-Jones

OpenCV's `haarcascade_frontalface_default.xml` is a trained Viola-Jones detector
(Viola and Jones, 2001). Three ideas make it work, and all three are worth knowing.

**Haar-like features.** A feature is two to four adjacent rectangles; its value is the
sum of the pixels under the white rectangles minus the sum under the black ones. A
horizontal two-rectangle feature laid across the eyes and cheeks fires on a face,
because the eye band is darker than the cheeks below it; a three-rectangle feature
across the bridge of the nose fires because the bridge is lighter than the eyes either
side. One feature is a weak test. In a 24x24 window there are about 160,000 of them
(every rectangle shape, size and position), far too many to evaluate.

**The integral image.** Precompute, for every pixel, the sum of all pixels above and to
the left of it: `ii(x, y) = sum of I(x', y') for x' <= x, y' <= y`. One pass over the
image does it. After that, the sum of any rectangle, at any size, is four lookups:
`ii(D) - ii(B) - ii(C) + ii(A)` for its corners. So a feature costs the same six to nine
memory reads whether it spans four pixels or four hundred, and searching a larger scale
costs no more per feature than a small one.

**AdaBoost, then a cascade.** AdaBoost picks a few features out of the 160,000 and
weights them: each round trains every feature as a one-threshold classifier (a
decision stump), keeps the one with the lowest weighted error, and increases the
weight of the training examples it got wrong so the next round looks for a feature
that handles those. The result is a strong classifier that is a weighted vote of weak
ones. Viola and Jones then chain several of these into a **cascade**: stage one uses a
handful of features and is tuned to pass nearly every face while rejecting a large
share of non-faces; each later stage is larger and runs only on the windows that
survived. Almost every window in an image is not a face, and almost all of them are
thrown out in the first stage or two, so the average cost per window is a few dozen
features, not thousands.

The cascades zeg uses, counted from the XML files OpenCV ships:

| Cascade | Window | Stages | Weak classifiers | First stage |
| --- | --- | ---: | ---: | ---: |
| `haarcascade_frontalface_default` | 24x24 | 25 | 2,913 | 9 |
| `haarcascade_profileface` | 20x20 | 26 | 2,609 | 3 |
| `haarcascade_eye` | 20x20 | 24 | 1,066 | 6 |
| `haarcascade_eye_tree_eyeglasses` | 20x20 | 30 | tree stages | |

`detectMultiScale` slides the window over the image at every position and over a
pyramid of scales (each 1.1 times the last), and keeps a detection only where at least
`minNeighbors` overlapping windows agree (5 for faces). That grouping is what stops a
single lucky window from becoming a face.

What zeg does with it, per frame (`src/detector.cpp`):

1. Scale the frame to 320 pixels wide, grayscale, and equalise the histogram so a dim
   webcam and a bright one look alike to the features. Faces smaller than a tenth of
   the frame width are not searched for. This step is most of the speed.
2. Run the frontal cascade. Two or more faces: **multiple faces**. One: go on to the
   eyes.
3. No frontal face: run the profile cascade on the frame and on its mirror image. The
   profile cascade was trained on one orientation only (nose to the image left), so the
   mirror finds the other. A profile is a head turned roughly 60 to 90 degrees:
   **looking away**, to the side the nose points. Nothing at all: **no face**.

## 2. Where are the eyes pointing

Inside a frontal face, eyes sit in a band from about 18 to 58 percent of the way down
the face box. zeg searches each half of that band separately with `haarcascade_eye`,
falling back to `haarcascade_eye_tree_eyeglasses` when it finds nothing (frames catch
the plain eye cascade on their edges). It keeps the largest detection per side.

**The pupil.** A Haar eye box contains the brow at the top and lid shadow at the
bottom, so the top quarter and the bottom fifth are cut off. In what is left
(`locate_pupil`):

1. Gaussian blur (kernel about a twelfth of the eye width) to remove lashes and noise.
2. Stretch the contrast to 0-255, then keep the darkest 10 percent of pixels. The
   pupil and iris are the darkest compact thing in an eye; skin and sclera are not.
3. Morphological opening to remove specks, then connected components.
4. Score each component by area, times how central it is, divided by how many patch
   borders it touches (brow shadow and lash lines run into the border; a pupil
   usually does not). A component touching three or four borders is a band of shadow
   and is rejected.
5. The pupil is the darkness-weighted centroid of the winning component, from the
   image moments: `x = sum(w x) / sum(w)`, with `w` how much darker than the cut each
   pixel is.

The pupil's offset from the centre of the patch, as a fraction of its width, is the eye
reading: positive is toward the image right. With both eyes found, the midpoint between
them compared with the centre of the face box is a cheap **head yaw** reading: when the
head turns, the eyes slide toward one side of the face box before the frontal cascade
loses the face. The horizontal offset used for classification is
`pupil offset + 1.5 x yaw`. The vertical offset is the pupil's alone.

**Baseline.** Offsets are measured against the candidate's own median over the last 30
seconds of frontal frames. A laptop camera sits above the screen, so a candidate reading
the screen looks slightly down relative to the camera for the whole call; without the
baseline that is "looking down" forever. The same window tracks how often the eyes are
found at all: for someone whose eyes are usually found, a frontal face with no eyes is
lids lowered, which is **looking down**; for someone whose eyes are rarely found
(glasses glare, low light), missing eyes mean nothing and the frame counts as on screen.

**The call per frame** (`classify` in `src/segments.cpp`):

| Seen | Label |
| --- | --- |
| two or more faces | multiple faces |
| no face | no face |
| a profile, nose to the image right | looking away, candidate's left |
| a profile, nose to the image left | looking away, candidate's right |
| frontal, no eyes, eyes usually found | looking away, down |
| frontal, horizontal offset beyond +/-0.20 | looking away, left or right |
| frontal, pupil lower than +0.16 of the eye height | looking away, down |
| otherwise | on screen |

Looking up is never flagged: it is what people do while they think.

Left and right are the candidate's own. A browser sends the camera unmirrored (the
self-view mirror is CSS only), so a candidate turning to their left moves toward the
right of the image.

## 3. From frames to spans

**Smoothing.** Single frames are noisy: a blink looks like looking down, a pupil
threshold catches a lash for one frame. Two centred windows of nine frames each (0.6 s
at 15 fps) remove it: the offsets of each frame are replaced by the median over the
window before classifying, and the label is then replaced by the majority label over
the window. The cost is about 0.6 s of latency, which nothing downstream minds, since a
flag needs five seconds of evidence.

**Spans** (`Segmenter`). Frames are grouped into runs by reason: looking away (left,
right and down together, so glancing from one side to the other is one continuous
look away), no face, multiple faces. An interruption shorter than 0.5 s does not end a
run. A run is flagged when it lasts at least its threshold:

| Reason | Threshold | Why |
| --- | --- | --- |
| looking away | 5 s | plan.md, stage 5: gaze beyond 30 to 45 degrees for more than 5 seconds |
| no face | 5 s (follows `--threshold`) | leaning out to grab a charger is not worth a reviewer's time |
| multiple faces | 2 s | a second person in view is worth a look even briefly |

Flagged runs of one reason less than 1 s apart are merged. Each flag carries its
direction (for looking away: left, right, down, or mixed when no side has 60 percent of
the frames), a confidence, and the index of the frame in the middle of the span, which
`--samples` saves as a JPEG. **Confidence** is the share of the span's raw, unsmoothed
frames that agree with the flag, each weighted by how clearly it read (how far past the
threshold its offset was). A 0.9 is a span where nearly every frame said the same
thing; a 0.5 is one the smoothing had to argue for.

Live, a flag is released as soon as it can no longer grow or merge: one second after
it ends. `Session.take_closed()` returns it then; `finish()` closes whatever is open at
hangup.

## 4. Validation

Three layers, from the smallest piece up. Everything here runs on a laptop with
`make test-vision` and `make vision-eval`.

**Unit tests** (GoogleTest, `services/vision/tests`, 28 tests). The pupil finder on
drawn eyes, where the answer is known to the pixel, including noise and a dim exposure;
per-frame classification from constructed observations; the segmenter's thresholds,
gap tolerance, merging, confidence and live release; the JSON shape; and the whole
pipeline on five public-domain and CC photographs held as frames: three frontal
portraits (one with glasses) read as on screen, mirrored and shifted too; a head in
profile reads as looking away and its mirror as the other side; an empty room is no
face; two portraits side by side are multiple faces. One profile photograph (a man in
a patterned cap, soft light) is missed by OpenCV's profile cascade at every setting
tried; the test pins that as a known miss rather than hiding it.

**Integration tests** (pytest). The gateway's `GazeReview` against a fake detector
(the sink never blocks, frames past 15 fps are skipped, a backlog is dropped, a bad
frame does not end the review, flags come back on the call clock) and against the real
module (a candidate who leaves the frame for 7 s gets one "no face" flag at 4 to 11 s).
The report section's wording, order and placement, and that the score, band and flags
are identical with and without video flags.

**Labelled clips.** Two sets, each split into dev (the only clips looked at while
choosing parameters) and test (run once, reported here):

- *Real*: 8 clips from Wikimedia Commons (public domain or CC BY / BY-SA; sources and
  licenses in `services/vision/eval/DATA.md`), 10 to 45 s each, 682 labels. Labelled
  by hand every 0.5 s from the frames, without looking at any detector output, with the
  split fixed by a hash of the clip names before labelling. They are what could be
  found with a permissive license, not webcam calls: one real Skype webcam recording,
  two people talking straight to camera, an interview subject answering someone off
  camera, a news package, a TV talk show and a phone selfie. Downloaded and re-encoded
  by `eval/fetch_clips.py`, not committed.
- *Synthetic*: 12 clips of 45 s from `zeg-gaze-synth`, built from the same five
  photographs over a drawn room: the frontal portrait swaying, drifting in brightness
  and wandering around the frame; a profile photograph (mirrored for the other side)
  for a head turned away; an empty room or only the shoulders for no face; two
  portraits for multiple faces. Event lengths are drawn from 1 to 10 s so that many
  fall under the thresholds and must not be flagged. Ground truth is exact.

Ground-truth spans come from the labels by the detector's own rules (thresholds, the
0.5 s gap, the 1 s merge). A flag matches a true span when the reason is the same and
their intersection over union is at least 0.5, one to one. "Any reason" ignores the
reason, which counts a head turned past the profile cascade that was flagged as "no
face".

Results on the **test** split:

| Set | Clips | True spans | Flags | Matched | Precision | Recall | Recall, any reason |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Real | 6 | 8 | 3 | 2 | 67% (2/3) | 25% (2/8) | 25% |
| Synthetic | 8 | 20 | 17 | 12 | 71% (12/17) | 60% (12/20) | 85% (17/20) |

| Set | Reason | True spans | Flags | Matched |
| --- | --- | ---: | ---: | ---: |
| Real | looking away | 4 | 1 | 1 |
| Real | no face | 1 | 1 | 1 |
| Real | multiple faces | 3 | 1 | 0 |
| Synthetic | looking away | 9 | 3 | 3 |
| Synthetic | no face | 7 | 10 | 5 |
| Synthetic | multiple faces | 4 | 4 | 4 |

For reference, the dev split: synthetic 90% precision and 82% recall (4 clips, 11
spans); real 0 of 2 spans found (below).

What the numbers say, read clip by clip:

- **When it flags, it is usually right, and it does not flag people talking to the
  camera.** The two clips closest to a candidate on a call (an astronaut and a speaker
  talking straight to camera, 90 s together) produced no flags. On docs/zeg-demo.mp4,
  which shows slides and a robot avatar and no person, every one of 3,601 frames reads
  "no face" and nothing else.
- **It misses a lot on real footage.** Three of the eight real spans are two faces
  where one is small (a news anchor beside a face on a studio monitor, about 35 px
  wide) or half out of frame (the selfie in dev): below the minimum face size of a
  tenth of the frame width, or not a whole face, so Haar never sees two. The looking-
  away misses are 45 degree three-quarter turns, the gap between the frontal and
  profile cascades, and a downward look in a soft 320x240 Skype recording. The one
  false flag is two seconds of "multiple faces" on a talk show host.
- **In the synthetic set, most misses are one photograph.** Of the 8 missed spans, 5
  are head turns that used the profile photograph the profile cascade cannot see, so
  they were flagged, correctly timed, as "no face" instead (hence 85% with the reason
  ignored). Two are no-face spans of exactly 5.0 s, on the threshold. The last is a
  10 s head turn that was not flagged at all: its frames flickered between "profile"
  and "no face", so neither run lasted 5 s on its own. Counting a turned head and a
  vanished one toward one span would fix it; that was found on the test split, so it
  is left as a follow-up rather than tuned in and re-reported. Timing is tight:
  matched flags start and end within about half a second of the truth.
- **Per sample**, on the real test clips, 68% of the 534 labels match the detector's
  smoothed label. It rarely calls a person on screen "away" (41 of 320 on-screen
  samples, mostly "down" from a frontal face whose eyes were not found for a moment),
  and it misreads "multiple faces" as one face most of the time, for the reasons above.
- **The eye reading is the weakest part.** The pupil is found reliably (the unit tests
  and the drawn overlays agree), but a Haar eye box re-centres on the iris, so the
  pupil's offset from the box barely moves when only the eyes turn. The dev interview
  clip, where the subject's head is turned about 25 degrees and her eyes further, reads
  as on screen for its whole 40 s. Head turns large enough to lose the frontal face are
  what the detector catches.

Nothing was tuned on the test split. The parameters that changed during development
(the profile cascade's finer scale step, requiring an eye in a second face, dropping
overlapping face boxes, and pinning the missed profile photograph) came from the unit
test photographs and the dev clips, and the test split was run once at the end.

### Speed

`zeg-gaze` on an Apple M5 laptop, one thread, Release build, 640x480 input, decode
included, three runs each:

| Clip (640x480) | Frames per second |
| --- | ---: |
| a person talking to camera (`kelly_iss_message`) | 195 to 200 |
| an interview, head slightly turned (`bokova_unesco_interview`) | 244 to 248 |
| synthetic, frequent no-face and profile frames (`synth_04`, `synth_07`) | 125 to 145 |

The camera sends 15 fps, so one core runs 8 to 16 times faster than real time. Frames
with no frontal face are the slow ones: they run the profile cascade twice, on the
frame and its mirror, at a finer scale step. 1080p input is scaled to 640 wide first
(the demo video, 1920x1080, ran at 242 fps).

### End to end

A real WebRTC call into the gateway, with a synthetic clip as the camera
(`services/gateway/tools/video_call_smoke.py`: aiortc on both ends over loopback, SDP
offer and answer over HTTP, VP8 encoded and decoded): all 674 frames were analysed,
none dropped, and at hangup the gateway logged

```
Video review, moments for a human to watch:
  [00:03-00:08] Looking away from the screen, to their right, for 5 s. Detector agreement 78%.
  [00:11-00:20] No face in view for 9 s. Detector agreement 80%.
  [00:37-00:42] Looking away from the screen, to their right, for 6 s. Detector agreement 79%.
  These mark video to watch, not conclusions. People look away to think, read notes, or
  check a second screen, and a face drops out when a camera moves. Watch the moment
  before weighing it; none of it is in the score.
```

against a truth of looking away at 3.5 to 8.5 s, no face at 12 to 20.5 s, and looking
away at 37 to 43 s. The same clip through the command line tool and
`python -m zeg.cli --video-flags flags.json` puts the identical section into the
scored report, after the flags and before "A human reviews this before any decision".
This was the first time video crossed the gateway's WebRTC path at all; audio from a
real browser remains untested (services/gateway/HANDOFF.md).

## 5. What it does not handle well

- **The gap between frontal and profile.** The frontal cascade loses a face at roughly
  30 to 40 degrees of yaw and the profile cascade finds it from roughly 60. In between,
  often nothing fires, and a head turned 45 degrees is reported as **no face** rather
  than looking away. The eval's "any reason" column counts how often that happens.
- **Eyes alone.** A candidate who keeps their head still and moves only their eyes to a
  second monitor moves the pupil a few pixels at webcam resolution, and the Haar eye
  box tends to move with the iris, so the offset measured against the box stays small.
  The pupil itself is found; its offset is a weak signal. Head turns are what the
  detector catches reliably. Measuring the pupil against the eye corners, or a landmark
  model, is the next step if eye-only gaze matters.
- **Glasses.** Reflections on lenses break the darkest-blob assumption and often hide
  the eyes from the eye cascade. The eyeglasses cascade helps with detection, not with
  the pupil. The "eyes usually found" rule stops a wearer from being flagged as looking
  down all call, at the cost of not seeing down-glances for them at all.
- **Lighting and skin tone.** Haar features compare brightness between regions. Strong
  backlight, a dim room, or low contrast between skin and eyes weakens every stage, and
  the stock cascades were trained on datasets from the early 2000s that do not
  represent everyone equally. A detector that finds some faces less reliably flags
  those candidates more often, for "no face" in particular. This is the most important
  reason the flags are for review only; before any real use, the flag rate needs
  checking across skin tones and lighting the way docs/05 asks for scoring.
- **Webcam angle.** The baseline absorbs a constant angle. A camera far off to one side
  (an external monitor with the laptop beside it) makes the candidate's normal gaze
  read as a head turn for the first `baseline_min_frames` frames and noisier after.
- **Pictures of faces.** A poster, a photo on the wall, or a face on a second screen is
  a second face to a Haar cascade. The two-second threshold and the smoothing do not
  help with something that never moves.
- **A turn that flickers between reasons.** A head turned near the edge of what the
  profile cascade finds alternates between "looking away" and "no face" frame to frame.
  Each reason is a separate run, so a long turn can end up flagged as neither.
- **Small and partial faces.** Faces narrower than a tenth of the frame, and faces cut
  by the frame edge, are not found. For the candidate that is fine at webcam distance;
  it means a second person far behind them, or leaning in at the edge, can be missed.
- **Looking down vs eyes closed.** Both read as lids lowered. A candidate who closes
  their eyes to think for six seconds is flagged as looking down.

## 6. Why these are flags for review, and nothing more

zeg recommends and a human decides (docs/06-compliance.md, non-negotiable 3), and the
video review is held to a stricter version of the same rule: it is not an input to the
recommendation at all. The reasons are specific.

- **Looking away is ordinary.** People look away to think, to recall, to read notes the
  interviewer allowed, to glance at a second monitor that holds the call window. A
  detector cannot see which.
- **Eye contact is not universal.** Norms around eye contact differ across cultures,
  and many candidates, including autistic candidates and candidates with nystagmus,
  strabismus or low vision, look at a screen differently. Scoring on it would be
  disability and origin discrimination by proxy, which is exactly what the bias
  testing in docs/05 exists to catch.
- **The detector is uneven.** See the lighting and skin tone point above.
- **Video is regulated separately.** The Illinois Artificial Intelligence Video
  Interview Act covers analysis of interview video; the EU AI Act treats candidate
  evaluation as high-risk. docs/06 already notes that audio-only is one reason to keep
  video optional. Any deployment that turns this on needs counsel's review first, and
  candidate notice that the camera, if sent, is analysed.

So the report says what was seen, when, and for how long, in plain words, and says in
the same section that these are moments to watch, not conclusions. The wording never
guesses at intent, and a test pins that it never uses words like "cheating" or
"suspicious". A reviewer who cares opens the recording at the timestamp and decides.

## Knobs

| Setting | Default | Where |
| --- | --- | --- |
| looking-away threshold | 5 s | `--threshold`, `Session(threshold_s=)` |
| no-face threshold | same as looking away | `--no-face-threshold` |
| multiple-faces threshold | 2 s | `--multi-face-threshold` |
| smoothing window | 9 frames | `--smooth`, `Session(smooth_window=)` |
| horizontal / down offset | 0.20 / 0.16 | `Config` in `gaze.hpp` |
| gap that does not end a run | 0.5 s | `Config::max_gap_s` |
| merge gap | 1.0 s | `Config::merge_gap_s` |
| detector frame rate cap | 15 fps | `GazeReview(max_fps=)` |
