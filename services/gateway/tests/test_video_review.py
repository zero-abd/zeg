"""The video_sink seam: live frames to the gaze detector, flags out at hangup.

The first half runs anywhere, against a fake detector session, and pins the threading
contract: the sink never blocks the event loop, frames beyond the detector's rate are
skipped, a backlog is dropped rather than queued, and a bad frame does not end the
review. The second half runs the real C++ module (services/vision, `make vision`) and
is skipped when it is not built.
"""

import glob
import json
import os
import threading
import time

import pytest

from gateway import video_review
from gateway.video_review import GazeReview, analyse_recording, save_flags, to_bgr
from zeg.video_review import flags_from, render_video_review

STILLS = os.path.join(video_review._REPO, "services", "vision", "tests", "fixtures", "stills")


class FakeSession:
    """zeg_gaze.Session's shape. Flags a span every `every` frames."""

    def __init__(self, delay=0.0, every=0, fail_on=()):
        self.pushed = []
        self.delay = delay
        self.every = every
        self.fail_on = set(fail_on)
        self.closed = []

    def push_bgr(self, data, width, height, stride, t_s):
        if len(self.pushed) in self.fail_on:
            self.pushed.append(None)
            raise ValueError("corrupt frame")
        if self.delay:
            time.sleep(self.delay)
        self.pushed.append((len(data), width, height, stride, t_s))
        if self.every and len(self.pushed) % self.every == 0:
            self.closed.append({"start_s": t_s - 1, "end_s": t_s + 5, "reason": "looking_away",
                                "direction": "left", "confidence": 0.9, "sample_frame": 1})
        return []

    def take_closed(self):
        out, self.closed = self.closed, []
        return out

    def finish(self):
        return [{"start_s": 0.5, "end_s": 7.0, "reason": "no_face", "confidence": 0.8,
                 "sample_frame": 3}]


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def raw(frame):
    """Converter for the fake frames: already (bytes, w, h, stride)."""
    return frame


FRAME = (b"\x00" * (640 * 480 * 3), 640, 480, 640 * 3)


def _wait_for(pred, timeout=2.0):
    end = time.time() + timeout
    while time.time() < end and not pred():
        time.sleep(0.005)
    assert pred()


def test_frames_reach_the_detector_on_the_call_clock():
    clock = Clock()
    session = FakeSession()
    review = GazeReview(session=session, clock=clock, started_at=90.0, converter=raw, queue_size=100)
    for _ in range(5):
        review.sink(FRAME, 0)
        _wait_for(lambda: len(session.pushed) == review.received)
        clock.t += 0.1
    flags = review.finish()
    times = [p[4] for p in session.pushed]
    assert times == pytest.approx([10.0, 10.1, 10.2, 10.3, 10.4])
    assert session.pushed[0][:4] == (640 * 480 * 3, 640, 480, 1920)
    assert [f["reason"] for f in flags] == ["no_face"]


def test_frames_faster_than_max_fps_are_skipped():
    clock = Clock()
    session = FakeSession()
    review = GazeReview(session=session, clock=clock, max_fps=15, converter=raw, queue_size=1000)
    for _ in range(60):  # two seconds of a 30 fps camera
        review.sink(FRAME, 0)
        clock.t += 1 / 30
    review.finish()
    assert review.received == 60
    assert 28 <= len(session.pushed) <= 31


def test_a_slow_detector_drops_frames_instead_of_blocking_the_sink():
    clock = Clock()
    session = FakeSession(delay=0.05)
    review = GazeReview(session=session, clock=clock, max_fps=0, converter=raw, queue_size=2)
    started = time.perf_counter()
    for _ in range(50):
        review.sink(FRAME, 0)
        clock.t += 0.01
    elapsed = time.perf_counter() - started
    assert elapsed < 0.05, "the sink runs on the event loop and must not wait on the detector"
    review.finish()
    assert review.dropped > 0
    assert review.analysed + review.dropped == 50


def test_flags_that_close_during_the_call_are_kept_and_sorted_with_the_rest():
    clock = Clock()
    session = FakeSession(every=3)
    review = GazeReview(session=session, clock=clock, started_at=100.0, converter=raw, queue_size=100)
    for _ in range(6):
        review.sink(FRAME, 0)
        _wait_for(lambda: len(session.pushed) == review.received)
        clock.t += 1.0
    assert len(review.flags_so_far()) == 2
    flags = review.finish()
    assert [f["reason"] for f in flags] == ["no_face", "looking_away", "looking_away"]
    assert review.finish() is flags  # idempotent: teardown can run twice


def test_a_bad_frame_does_not_end_the_review():
    clock = Clock()
    session = FakeSession(fail_on={1})
    review = GazeReview(session=session, clock=clock, converter=raw, queue_size=100)
    for _ in range(4):
        review.sink(FRAME, 0)
        _wait_for(lambda: len(session.pushed) == review.received)
        clock.t += 0.1
    review.finish()
    assert review.errors == 1
    assert review.analysed == 3


def test_the_sink_is_safe_to_call_from_another_thread_while_the_worker_runs():
    clock = Clock()
    session = FakeSession()
    review = GazeReview(session=session, clock=time.monotonic, max_fps=0, converter=raw, queue_size=4)
    threads = [threading.Thread(target=lambda: [review.sink(FRAME, 0) for _ in range(50)]) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    review.finish()
    assert review.analysed + review.dropped == 200
    del clock


def test_to_bgr_asks_pyav_for_640x480_bgr24():
    class Plane(bytes):
        line_size = 1920

    class Converted:
        width, height = 640, 480
        planes = [Plane(b"\x01" * 1920 * 480)]

    class Frame:
        def reformat(self, width, height, format):
            assert (width, height, format) == (640, 480, "bgr24")
            return Converted()

    data, w, h, stride = to_bgr(Frame())
    assert (len(data), w, h, stride) == (1920 * 480, 640, 480, 1920)


def test_the_flags_render_as_the_report_section_and_save_for_scoring(tmp_path):
    flags = FakeSession().finish()
    lines = render_video_review(flags_from(flags))
    assert lines[1].startswith("  [00:00-00:07] No face in view for 6 s.")
    path = save_flags(flags, str(tmp_path / "call"))
    assert json.load(open(path)) == flags


def test_a_recording_falls_back_to_the_cli_when_the_module_is_missing(tmp_path, monkeypatch):
    fake = tmp_path / "zeg-gaze"
    fake.write_text(
        "#!/bin/sh\n"
        "echo '[{\"start_s\": 1.0, \"end_s\": 7.5, \"reason\": \"no_face\", \"confidence\": 0.8, "
        "\"sample_frame\": 60}]'\n"
    )
    fake.chmod(0o755)
    monkeypatch.setattr(video_review, "load_module", lambda: None)
    monkeypatch.setattr(video_review, "cli_path", lambda: str(fake))
    flags = analyse_recording("call.avi")
    assert flags[0]["reason"] == "no_face" and flags[0]["end_s"] == 7.5


def test_without_the_module_or_the_cli_the_error_says_how_to_build_it(monkeypatch):
    monkeypatch.setattr(video_review, "load_module", lambda: None)
    monkeypatch.setattr(video_review, "cli_path", lambda: None)
    with pytest.raises(RuntimeError, match="make vision"):
        analyse_recording("call.avi")


# --- the real detector ---------------------------------------------------------------

zeg_gaze = video_review.load_module()
needs_module = pytest.mark.skipif(zeg_gaze is None, reason="zeg_gaze not built (make vision)")


def _frontal_still():
    found = sorted(glob.glob(os.path.join(STILLS, "frontal_*.jpg")))
    if not found:
        pytest.skip("no face stills in services/vision/tests/fixtures/stills")
    return found[0]


def _webcam_frame(data, width, height):
    """Scale a still to 480 rows (nearest neighbour) and centre it on a 640x480 canvas."""
    scale = 480.0 / height
    out_w = min(640, int(width * scale))
    x0 = (640 - out_w) // 2
    cols = [min(width - 1, int(x / scale)) * 3 for x in range(out_w)]
    canvas = bytearray(b"\x7a" * (640 * 480 * 3))
    for y in range(480):
        src = data[min(height - 1, int(y / scale)) * width * 3:][: width * 3]
        row = b"".join(src[c:c + 3] for c in cols)
        start = (y * 640 + x0) * 3
        canvas[start:start + len(row)] = row
    return bytes(canvas)


@needs_module
def test_the_real_detector_flags_a_candidate_who_left_the_frame():
    data, w, h = zeg_gaze.read_image(_frontal_still())
    face = _webcam_frame(data, w, h)
    empty = b"\x7a" * (640 * 480 * 3)
    clock = Clock()
    review = GazeReview(clock=clock, started_at=100.0, converter=lambda f: (f, 640, 480, 1920),
                        queue_size=1000)
    # 4 s on camera, 7 s gone, 4 s back, at 15 fps.
    for secs, frame in ((4, face), (7, empty), (4, face)):
        for _ in range(secs * 15):
            review.sink(frame, 0)
            clock.t += 1 / 15
    flags = review.finish()
    assert review.dropped == 0
    assert [f["reason"] for f in flags] == ["no_face"]
    assert flags[0]["start_s"] == pytest.approx(4.0, abs=0.5)
    assert flags[0]["end_s"] == pytest.approx(11.0, abs=0.5)
    assert "No face in view for 7 s." in "\n".join(render_video_review(flags_from(flags)))


@needs_module
def test_the_module_rejects_a_buffer_smaller_than_the_frame():
    session = zeg_gaze.Session()
    with pytest.raises(ValueError):
        session.push_bgr(b"\x00" * 100, 640, 480, 0, 0.0)
