"""The candidate's camera, watched for moments a human should review.

This fills the `video_sink` seam in webrtc.py. Each inbound frame is scaled to
640x480 BGR and handed to the C++ detector (services/vision, `import zeg_gaze`, a
pybind11 module) on a worker thread, so a slow frame never holds up the event loop
that carries the call's audio. Frames arrive at whatever rate the browser sends; the
detector sees at most `max_fps` of them, and when it falls behind the newest frames
are dropped rather than queued, because a flag needs seconds of evidence and a
backlog only adds lag.

When the module is not built, `GazeReview.available()` is False and the gateway runs
exactly as before: video is optional (docs/06-compliance.md, and the candidate page
says the screen is audio only). The same flags can be produced after the call from a
recording with `analyse_recording`, which uses the module or, failing that, the
`zeg-gaze` command line tool.

Flags are moments to watch, not findings. They go to the report's "Video review"
section (zeg.video_review) and nowhere near the scorer.
"""

import importlib
import json
import logging
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from typing import Callable, List, Optional

log = logging.getLogger("gateway.video_review")

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
#: Where `make vision` leaves the module and the CLI.
VISION_BUILD = os.environ.get("ZEG_GAZE_BUILD", os.path.join(_REPO, "services", "vision", "build"))

FRAME_WIDTH = 640
FRAME_HEIGHT = 480


def load_module():
    """`zeg_gaze`, from the path or the vision build directory; None when not built."""
    try:
        import zeg_gaze  # noqa: F401

        return zeg_gaze
    except ImportError:
        pass
    if os.path.isdir(VISION_BUILD) and VISION_BUILD not in sys.path:
        sys.path.append(VISION_BUILD)
        importlib.invalidate_caches()
        try:
            import zeg_gaze

            return zeg_gaze
        except ImportError:
            sys.path.remove(VISION_BUILD)
    return None


def cli_path() -> Optional[str]:
    """The `zeg-gaze` binary, from the build directory or PATH."""
    built = os.path.join(VISION_BUILD, "zeg-gaze")
    if os.path.isfile(built) and os.access(built, os.X_OK):
        return built
    return shutil.which("zeg-gaze")


def to_bgr(frame, width: int = FRAME_WIDTH, height: int = FRAME_HEIGHT):
    """A PyAV VideoFrame as (bgr bytes, width, height, stride).

    PyAV does the scale and the colour conversion in one libswscale pass. Anything with
    the same `reformat` shape works, which is what the tests use.
    """
    bgr = frame.reformat(width=width, height=height, format="bgr24")
    plane = bgr.planes[0]
    return bytes(plane), bgr.width, bgr.height, plane.line_size


class GazeReview:
    """Live review of one call's video. Use `sink` as webrtc.consume_video's video_sink.

    `session` is anything with the zeg_gaze.Session methods (push_bgr, take_closed,
    finish); by default a real one. `clock` gives seconds; the flag times are on the
    call clock, measured from `started_at` (by default the first frame).
    """

    def __init__(
        self,
        session=None,
        max_fps: float = 15.0,
        clock: Callable[[], float] = time.monotonic,
        started_at: Optional[float] = None,
        threshold_s: float = 5.0,
        converter: Callable = to_bgr,
        queue_size: int = 2,
    ) -> None:
        if session is None:
            module = load_module()
            if module is None:
                raise RuntimeError("zeg_gaze is not built: run `make vision`")
            session = module.Session(threshold_s=threshold_s)
        self._session = session
        self._clock = clock
        self._t0 = started_at
        self._min_step = 1.0 / max_fps if max_fps > 0 else 0.0
        self._next_due = 0.0
        self._convert = converter
        self._queue: "queue.Queue" = queue.Queue(maxsize=queue_size)
        self._lock = threading.Lock()
        self._flags: List[dict] = []
        self._finished: Optional[List[dict]] = None
        self.received = 0
        self.analysed = 0
        self.dropped = 0
        self.errors = 0
        self._worker = threading.Thread(target=self._run, name="gaze-review", daemon=True)
        self._worker.start()

    @staticmethod
    def available() -> bool:
        return load_module() is not None

    def sink(self, frame, count: int = 0) -> None:
        """Called on the event loop for every inbound video frame. Never blocks."""
        self.received += 1
        now = self._clock()
        if self._t0 is None:
            self._t0 = now
        t = now - self._t0
        # A schedule, not a minimum gap: a 30 fps camera gives exactly 15 fps, where
        # "at least 1/15 s since the last one" loses frames to rounding and gives 10.
        if t + 0.1 * self._min_step < self._next_due:
            return
        self._next_due = max(self._next_due, t - self._min_step) + self._min_step
        try:
            self._queue.put_nowait((frame, t))
        except queue.Full:
            self.dropped += 1

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            frame, t = item
            try:
                data, width, height, stride = self._convert(frame)
                self._session.push_bgr(data, width, height, stride, t)
                closed = self._session.take_closed()
                self.analysed += 1
            except Exception as exc:  # one bad frame must not end the review
                self.errors += 1
                if self.errors <= 3:
                    log.warning("gaze frame failed: %r", exc)
                continue
            if closed:
                with self._lock:
                    self._flags.extend(closed)

    def flags_so_far(self) -> List[dict]:
        """Flags that have closed during the call, for a live view."""
        with self._lock:
            return list(self._flags)

    def finish(self, timeout: float = 5.0) -> List[dict]:
        """End of call: drain the worker, close open spans, return every flag."""
        if self._finished is not None:
            return self._finished
        self._queue.put(None)
        self._worker.join(timeout)
        flags = self.flags_so_far() + list(self._session.finish())
        self._finished = sorted(flags, key=lambda f: f["start_s"])
        log.info(
            "video review: %d frames in, %d analysed, %d dropped, %d flags",
            self.received, self.analysed, self.dropped, len(self._finished),
        )
        return self._finished


def analyse_recording(path: str, threshold_s: float = 5.0, samples_dir: str = "") -> List[dict]:
    """Post-call: flags for a recorded video file, via the module or the CLI."""
    module = load_module()
    if module is not None:
        return list(module.process_video(path, threshold_s=threshold_s, samples=samples_dir)["flags"])
    exe = cli_path()
    if exe is None:
        raise RuntimeError("neither zeg_gaze nor zeg-gaze is built: run `make vision`")
    cmd = [exe, path, "--out", "-", "--quiet", "--threshold", str(threshold_s)]
    if samples_dir:
        cmd += ["--samples", samples_dir]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def save_flags(flags: List[dict], directory: str, name: str = "video_flags.json") -> str:
    """Write the flags beside the call's other artefacts for the scoring step."""
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, name)
    with open(path, "w") as fh:
        json.dump(flags, fh, indent=2)
    return path
