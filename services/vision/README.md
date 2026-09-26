# services/vision: video review with Haar cascades

`zeg-gaze` watches the candidate's camera, when they choose to send it, and marks
spans of the call for a human to review: looking away from the screen for more than
5 s, no face in view, more than one face in view. It is C++17 on OpenCV's Haar
cascades, with a command line tool for recorded video and a Python module that the
gateway feeds live frames to.

A flag is a moment to watch, never a finding. The report shows it under "Video
review" and the scorer never sees it. How it works, what the thresholds are and where
it fails: [docs/12-video-review.md](../../docs/12-video-review.md).

## Layout

```
include/zeg_gaze/gaze.hpp   the whole API: Detector, classify, Segmenter, Session, process_video
src/detector.cpp            Haar face (frontal, then profile both ways), eyes, pupil localisation
src/segments.cpp            per-frame classification, spans, merging, JSON
src/session.cpp             live pipeline: baseline, median + majority smoothing, segmenter; video files
tools/zeg_gaze_cli.cpp      zeg-gaze, the command line tool
tools/synth.cpp             zeg-gaze-synth, labelled synthetic clips from face stills
python/zeg_gaze_module.cpp  pybind11 module `zeg_gaze`
tests/                      GoogleTest: pupil, classification, segments, real face stills
eval/                       labelled clips (downloaded), eval.py (precision/recall of spans)
scripts/build_opencv.sh     minimal OpenCV from source, for a machine with no package for it
```

## Build

OpenCV 4 with its Haar cascade data, CMake 3.16+, a C++17 compiler. GoogleTest and
pybind11 are found if installed, otherwise GoogleTest is fetched and the Python module
is skipped.

| Machine | OpenCV |
| --- | --- |
| macOS | `brew install opencv` |
| Ubuntu, and the GB10 box (DGX OS is Ubuntu on arm64) | `sudo apt install libopencv-dev libgtest-dev pybind11-dev cmake` |
| Anything else | `services/vision/scripts/build_opencv.sh` (core, imgproc, objdetect, imgcodecs, videoio into `~/.local/opencv`, about 5 minutes) |

Then, from the repo root:

```bash
make vision-setup     # cmake, ninja, pybind11 and PyAV into .venv (skip if the system has them)
make vision           # builds services/vision/build/{zeg-gaze, zeg-gaze-synth, zeg_gaze*.so, zeg_gaze_tests}
make test-vision      # GoogleTest suite, then the gateway and report integration tests
```

`make vision` passes `OPENCV_DIR` to CMake when OpenCV lives somewhere it will not look
(the source build sets this up on its own). The cascade directory is found at configure
time and compiled in; override it with `ZEG_GAZE_CASCADES=/path/to/haarcascades` or
`--cascades`.

On Linux, `apt`'s OpenCV reads any video FFmpeg can. On a Mac, the Homebrew one does
too; the source build reads H.264/HEVC through AVFoundation and MJPEG AVI natively,
which is why the eval clips are stored as MJPEG AVI.

## Use

Recorded video:

```bash
services/vision/build/zeg-gaze call.mp4 --out flags.json [--threshold 5] \
    [--no-face-threshold 5] [--multi-face-threshold 2] [--samples stills/] [--per-frame frames.csv]
```

```json
[
  {
    "start_s": 192.40,
    "end_s": 200.87,
    "reason": "looking_away",
    "direction": "left",
    "confidence": 0.87,
    "sample_frame": 2958,
    "sample_t_s": 196.60
  }
]
```

`reason` is `looking_away`, `no_face` or `multiple_faces`. `direction` (looking away
only) is the candidate's own left, right, down, or mixed. `confidence` is the share of
the span's raw frames that agree with the flag, weighted by how clearly each frame
read. `sample_frame` is the middle frame of the span; `--samples DIR` saves it as a JPEG.

Live, from Python (the gateway does this in `services/gateway/gateway/video_review.py`):

```python
import zeg_gaze
session = zeg_gaze.Session(threshold_s=5.0)
for bgr_bytes, t in frames:                 # 640x480 BGR, seconds on the call clock
    session.push_bgr(bgr_bytes, 640, 480, 0, t)
    for flag in session.take_closed():      # each flag as soon as it can no longer grow
        ...
flags = session.finish()                    # end of call
zeg_gaze.process_video("call.mp4")          # or a recording, after the call
```

Live, from another language: `zeg-gaze --stdin --width 640 --height 480` reads frames
from stdin (an 8-byte little-endian double timestamp, then width x height x 3 bytes of
BGR) and prints each flag as a JSON line the moment it closes.

## Speed

Measured on an Apple M5 laptop, one thread, Release build, 640x480 input: see the
numbers in [docs/12-video-review.md](../../docs/12-video-review.md#speed). The camera
sends 15 fps, and the gateway never gives the detector more than that.
