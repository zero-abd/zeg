# Gaze / face-presence evaluation data

Ground truth for `services/vision`, labelled by hand from the frames. No detector output was
looked at while choosing clips, windows or labels.

## Fetching the clips

The videos are not committed. `fetch_clips.py` downloads each source file from Wikimedia
Commons by its exact URL, checks its sha256, trims it, and writes MJPEG-in-AVI clips that
OpenCV's built-in reader opens without FFmpeg:

```bash
.venv/bin/python services/vision/eval/fetch_clips.py                      # all clips
.venv/bin/python services/vision/eval/fetch_clips.py --only kelly_iss_message
```

It needs only PyAV (`pip install av`) and the standard library. Downloads are cached in
`services/vision/eval/.cache/` (about 80 MB), clips are written to
`services/vision/eval/clips/<id>.avi` (about 300 MB at 8 Mbit/s MJPEG). Both are
git-ignored. Re-running is a no-op unless `clips.json` changed; `--force` rebuilds.

Processing per clip, in this order: decode source time `[start_s, end_s)`; optional `crop`
`[x, y, w, h]` in source pixels; scale to 640 px wide (aspect kept, even height); resample to
a constant frame rate equal to the source rate (capped at 30 fps) by holding the latest
source frame at each output tick. **Output time 0 is `start_s`**, so label time `t` is source
time `start_s + t`. The output is deterministic (same bytes on every run).

If a sha256 check fails, the file on Commons was replaced. Do not relabel silently: re-check
the frames and update `clips.json` and `labels.json` together.

## Clips

| id | split | seconds | source window | what happens | license |
| --- | --- | --- | --- | --- | --- |
| `biden_fain_selfie` | dev | 34.0 | 0-34 s, cropped to the faces | Phone selfie, two men in frame the whole time | PD (PD-USGov-POTUS) |
| `bokova_unesco_interview` | dev | 40.0 | 20-60 s, cropped to head and shoulders | Interview subject answering an off-camera interviewer; turned to her right, repeated downcast stretches | CC BY-SA 3.0 IGO |
| `dempsey_dod_update` | test | 42.0 | 8-50 s | News package: anchor beside a monitor showing a face, general to camera, B-roll profile, 13.5 s text slide | PD (PD-USGov-Military-Army) |
| `kelly_iss_message` | test | 45.0 | 3-48 s, cropped to head and shoulders | Logo card, then an astronaut talking straight to camera | PD (PD-USGov-NASA) |
| `maher_odia_message` | test | 45.0 | 0-45 s | Fade in, then talking straight to camera outdoors | CC BY-SA 4.0 |
| `skype_vrinda_webcam` | test | 45.0 | 0-45 s, cropped to drop the caller's inset | Real 320x240 Skype webcam; looking down, back at the screen, two brief head turns | CC BY 3.0 |
| `valentin_wikimania_interview` | test | 45.0 | 45-90 s | Multi-camera interview: slight turn, 13 s strong three-quarter turn, then near frontal | CC BY 4.0 |
| `wol_voa_straight_talk` | test | 45.0 | 24-69 s | TV talk show: wide shot, host close-up turned away, guest close-up, 21.5 s two-shot | PD (PD-USGov-VOA) |

Sources, authors and exact file URLs:

- `biden_fain_selfie`: [President Biden records a selfie video with Shawn Fain of the UAW](https://commons.wikimedia.org/wiki/File:President_Biden_records_a_selfie_video_with_Shawn_Fain_of_the_UAW.webm), Joe Biden (Executive Office of the President), public domain as a work of the US federal government.
- `bokova_unesco_interview`: [UNESCO Director-General Irina Bokova interview on Palmyra](https://commons.wikimedia.org/wiki/File:UNESCO_Director-General_Irina_Bokova_interview_on_Palmyra.webm), UNESCO, [CC BY-SA 3.0 IGO](https://creativecommons.org/licenses/by-sa/3.0/igo/).
- `dempsey_dod_update`: [Dempsey Discusses Military Action in Ebola Response](https://commons.wikimedia.org/wiki/File:Dempsey_Discusses_Military_Action_in_Ebola_Response_141022-A-AB123-001.webm), DoD News / U.S. Army via DVIDS (video 368471), public domain.
- `kelly_iss_message`: [Astronaut Scott Kelly Speaks Out Against Bullying](https://commons.wikimedia.org/wiki/File:Astronaut_Scott_Kelly_Speaks_Out_Against_Bullying.webm), NASA Johnson Space Center, public domain.
- `maher_odia_message`: [Katherine Maher, Odia Wikipedia birthday - 3 July 2018](https://commons.wikimedia.org/wiki/File:Katherine_Maher,_Odia_Wikipedia_birthday_-_3_July_2018.webm), Wikimedia Foundation, [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
- `skype_vrinda_webcam`: [Vrinda-skype-5.ogv](https://commons.wikimedia.org/wiki/File:Vrinda-skype-5.ogv), Rahulkepapa, [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/).
- `valentin_wikimania_interview`: [Voices from Wikimania - Wikimedian Valentin](https://commons.wikimedia.org/wiki/File:Voices_from_Wikimania_%E2%80%93_Wikimedian_Valentin.webm), Hauke Kleinschmidt for Wikimedia Deutschland e.V., [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- `wol_voa_straight_talk`: [Straight Talk Africa Guest Ambassador Baak V.A. Wol on South Sudan](https://commons.wikimedia.org/wiki/File:Straight_Talk_Africa_Guest_Ambassador_Baak_V.A._Wol_on_South_Sudan.webm), Voice of America (VOA Africa), public domain.

The clips are trimmed, cropped and rescaled derivatives. Anyone redistributing the generated
`.avi` files must keep the attribution above and, for the CC BY-SA sources, the same license.
We only commit the recipe (`clips.json`), not the video.

### Split

Decided before any labelling: clip ids ranked by the hex sha256 of the id string; the two
lowest (`bokova_unesco_interview`, `biden_fain_selfie`) are **dev** (tune thresholds on
these), the other six are **test** (report on these, do not tune on them). Both splits
contain a clip with a long looking-away stretch (dev: bokova; test: valentin, wol).

### Label counts (0.5 s samples)

| id | samples | on_screen | away_left | away_right | away_down | no_face | multiple_faces |
| --- | --- | --- | --- | --- | --- | --- | --- |
| biden_fain_selfie | 68 | 0 | 0 | 0 | 0 | 0 | 68 |
| bokova_unesco_interview | 80 | 0 | 0 | 62 | 18 | 0 | 0 |
| dempsey_dod_update | 84 | 16 | 0 | 7 | 0 | 28 | 33 |
| kelly_iss_message | 90 | 85 | 0 | 0 | 0 | 5 | 0 |
| maher_odia_message | 90 | 89 | 0 | 0 | 0 | 1 | 0 |
| skype_vrinda_webcam | 90 | 72 | 2 | 0 | 15 | 1 | 0 |
| valentin_wikimania_interview | 90 | 56 | 0 | 34 | 0 | 0 | 0 |
| wol_voa_straight_talk | 90 | 2 | 2 | 38 | 2 | 0 | 46 |

## Labelling protocol (`labels.json`)

`labels.json` maps each clip id to `{"step_s": 0.5, "notes": "...", "samples": [[t, label], ...]}`
with `t = 0, 0.5, 1.0, ...` in output-clip seconds, up to the last frame. A sample describes the
frame on screen at time `t` (the last output frame with timestamp `<= t`).

Labels, exactly one per sample:

- `on_screen`: one face, head and eyes toward the camera/screen. Small glances, head tilts and
  reading-level eye movement stay `on_screen`. With a webcam above the screen, looking at the
  screen just below the lens is `on_screen`.
- `away_left` / `away_right`: head or eyes clearly pointed off camera sideways by roughly 30
  degrees or more (plan.md: flag gaze beyond 30-45 degrees). Direction is from the **person's
  own** perspective: turning to their own left moves the face toward **image right** in an
  unmirrored frame, and is `away_left`.
- `away_down`: clearly looking down (notes, phone, keyboard, lap), or eyes closed for a long
  stretch. Single blinks do not count.
- `no_face`: no face visible (left frame, cutaway, logo or text card, back of head).
- `multiple_faces`: two or more reasonably large faces visible, regardless of gaze. A face on
  a monitor or photo counts.

Every sample was labelled from contact sheets at 0.5 s steps, with face crops zoomed from the
640 px clip wherever the eyes mattered. When a sample was genuinely ambiguous the closest label
was used and the timestamp is listed in that clip's `notes`.

Known hard cases worth reading in `notes` before scoring:

- `bokova_unesco_interview` never looks into the lens; the whole clip is a moderate (25-35
  degree) turn toward the interviewer plus downcast eyes. Borderline for a 30 degree threshold.
- `valentin_wikimania_interview` 0-20 s is a 15-20 degree turn labelled `on_screen`; the
  20.5-33.5 s block is the clear away stretch.
- `dempsey_dod_update` anchor shots count the photo on the studio monitor as a second face;
  faces there are small (30-40 px wide).
- `wol_voa_straight_talk` host close-ups are turned about 45 degrees and also pitched down;
  labelled `away_right`. The 0-0.5 s wide shot has tiny faces.
- `skype_vrinda_webcam` is 320x240 source upscaled 2.7x; eyes are a few source pixels tall.

## Stills (`services/vision/tests/fixtures/stills/`)

Downscaled so the longer side is 640 px, JPEG quality 85, all under 120 KB. Checked by eye:
the frontal ones show both eyes open and looking at the camera; the profiles show a head turned
about 90 degrees (both face image left; mirror them for the other side).

| file | subject | source | author | license | edit |
| --- | --- | --- | --- | --- | --- |
| `frontal_1.jpg` | frontal, no glasses, studio background | [Anil Menon portrait (cropped)](https://commons.wikimedia.org/wiki/File:Anil_Menon_portrait_(cropped).jpg) | NASA / Robert Markowitz | Public domain (PD-USGov-NASA) | top 960x1200 of the 960 px thumbnail, scaled to 512x640 |
| `frontal_2.jpg` | frontal, no glasses, studio background | [Nichole Ayers portrait (cropped)](https://commons.wikimedia.org/wiki/File:Nichole_Ayers_portrait_(cropped).jpg) | NASA / Robert Markowitz | Public domain (PD-USGov-NASA) | top 960x1200, scaled to 512x640 |
| `frontal_glasses.jpg` | frontal, rimless glasses, studio background | [Raphael Warnock official photo (4x5 crop)](https://commons.wikimedia.org/wiki/File:Raphael_Warnock_official_photo_(4x5_crop).jpg) | U.S. Senate Photographic Studio, Rebecca Hammel | Public domain (PD-USGov-Congress) | scaled to 512x640 |
| `profile_1.jpg` | left-facing profile, outdoor, colour | [Muslim Man with Skullcap - Downtown Kampala - Uganda](https://commons.wikimedia.org/wiki/File:Muslim_Man_with_Skullcap_-_Downtown_Kampala_-_Uganda.jpg) | Adam Jones, Ph.D. | [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) | scaled to 480x640 |
| `profile_2.jpg` | left-facing profile, studio, black and white (19th-century carte de visite) | [Man profile portrait (5689483847)](https://commons.wikimedia.org/wiki/File:Man_profile_portrait_(5689483847).jpg) | Budtz Müller & Co., via Bergen Public Library | No known copyright restrictions (Flickr Commons) | cropped to the print (x 90-880, y 120-1000 of the 960 px thumbnail), scaled to 575x640 |

`profile_1.jpg` is a CC BY-SA 3.0 derivative (downscaled): keep the attribution above with it,
and it stays under CC BY-SA 3.0.
