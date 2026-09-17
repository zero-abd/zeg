"""The frame loop and the codec pipeline.

Both are testable without a model because neither contains one: the loop is
ordering plus accounting, and the codec wrapper is a one-frame delay. The model
underneath is the stand-in from `runtime.model`, which produces silence and is not
a model.
"""

import pytest

from zeg.runtime import protocol as p
from zeg.runtime.codec import PipelinedDecoder, pin_to_cores, silence
from zeg.runtime.loop import FrameLoop, QueueOverflow
from zeg.runtime.model import ModelPaths, ModelUnavailable, SilenceModel, build_model


class FakeClock:
    """A clock a test can move. No sleeping anywhere in this file."""

    def __init__(self):
        self.now = 0.0
        self.step_s = 0.0

    def __call__(self):
        value = self.now
        self.now += self.step_s
        return value


def collector():
    frames = []
    return frames, frames.append


# --- the loop ----------------------------------------------------------------


def test_the_loop_reports_its_own_death_to_whoever_is_waiting():
    """A model that raises on a commit or a fixed line produces no frame, so nothing
    prompts anyone to look at `error`: the client was told nothing and sat in silence
    until its own watchdog fired. This waits on an event, not on a clock."""
    import threading

    from zeg.runtime.session import FrameResult

    class Wedged:
        def step(self, pcm):
            return FrameResult()

        def commit_turn(self):
            raise RuntimeError("the device fell over")

    told = threading.Event()
    loop = FrameLoop(Wedged(), lambda result: None, on_error=lambda exc: told.set())
    loop.start()
    try:
        loop.commit_turn()
        assert told.wait(2.0), "the loop died without telling anyone"
        assert isinstance(loop.error, RuntimeError)
    finally:
        loop.stop()


def test_a_frame_produces_one_result():
    frames, sink = collector()
    loop = FrameLoop(SilenceModel(), sink)
    loop.submit_audio(b"\x00" * p.INPUT_FRAME_BYTES)
    assert loop.run_pending() == 1
    assert len(frames) == 1
    assert len(frames[0].audio_pcm) == p.OUTPUT_FRAME_BYTES


def test_work_is_processed_in_the_order_it_was_submitted():
    # A commit that overtakes unconsumed audio ends the turn before the model has
    # heard the end of it, which is the most expensive ordering bug here.
    order = []

    class Recorder(SilenceModel):
        def step(self, pcm):
            order.append("audio")
            return super().step(pcm)

        def commit_turn(self):
            order.append("commit")
            super().commit_turn()

    loop = FrameLoop(Recorder(), lambda result: None)
    loop.submit_audio(b"\x00" * p.INPUT_FRAME_BYTES)
    loop.submit_audio(b"\x00" * p.INPUT_FRAME_BYTES)
    loop.commit_turn()
    loop.run_pending()
    assert order == ["audio", "audio", "commit"]


def test_a_cancel_jumps_the_queue():
    # A cancel that waits behind five frames of audio is not a cancel.
    order = []

    class Recorder(SilenceModel):
        def step(self, pcm):
            order.append("audio")
            return super().step(pcm)

        def cancel_response(self, reason):
            order.append("cancel")

    loop = FrameLoop(Recorder(), lambda result: None)
    for _ in range(3):
        loop.submit_audio(b"\x00" * p.INPUT_FRAME_BYTES)
    loop.cancel("barge_in")
    loop.run_pending()
    assert order[0] == "cancel"
    assert order.count("audio") == 3, "the caller's audio is still delivered"


def test_over_budget_frames_are_counted():
    clock = FakeClock()
    frames, sink = collector()
    loop = FrameLoop(SilenceModel(), sink, budget_ms=80.0, clock=clock)

    clock.step_s = 0.05  # 50 ms, inside budget
    loop.submit_audio(b"\x00" * p.INPUT_FRAME_BYTES)
    loop.run_pending()
    assert loop.metrics.over_budget == 0
    assert frames[-1].over_budget is False

    clock.step_s = 0.095  # 95 ms, late
    loop.submit_audio(b"\x00" * p.INPUT_FRAME_BYTES)
    loop.run_pending()
    assert loop.metrics.over_budget == 1
    assert frames[-1].over_budget is True


def test_a_slow_control_operation_is_counted():
    """A briefing or a rollover seed is a prefill on the same serialized loop, and builds
    the same queue debt as a slow step. Only steps were timed, so the largest stall of a
    call went uncounted."""
    clock = FakeClock()
    frames, sink = collector()
    loop = FrameLoop(SilenceModel(), sink, budget_ms=80.0, clock=clock)
    clock.step_s = 0.4  # a 400 ms prefill
    loop.steer("Where we are: a seed hundreds of tokens long")
    loop.run_pending()

    assert loop.metrics.control_over_budget == 1
    assert loop.metrics.slowest_control == "steer"
    assert loop.metrics.frames == 0, "a control operation is not a frame"
    assert "control_over_budget=1" in loop.metrics.summary()
    assert "(steer)" in loop.metrics.summary()


def test_a_quick_control_operation_is_not_counted_as_late():
    clock = FakeClock()
    frames, sink = collector()
    loop = FrameLoop(SilenceModel(), sink, budget_ms=80.0, clock=clock)
    clock.step_s = 0.001
    loop.commit_turn()
    loop.run_pending()
    assert loop.metrics.control_over_budget == 0


def test_the_metrics_summary_says_what_happened():
    clock = FakeClock()
    clock.step_s = 0.09
    loop = FrameLoop(SilenceModel(), lambda result: None, clock=clock)
    for _ in range(3):
        loop.submit_audio(b"\x00" * p.INPUT_FRAME_BYTES)
    loop.run_pending()
    assert loop.metrics.frames == 3
    assert loop.metrics.over_budget == 3
    assert "over_budget=3" in loop.metrics.summary()


def test_a_backlog_is_fatal_rather_than_absorbed():
    # Dropping caller audio out of the middle of an utterance does not produce a
    # slightly worse transcript, it produces a confident wrong one.
    loop = FrameLoop(SilenceModel(), lambda result: None, max_queue=4)
    with pytest.raises(QueueOverflow):
        for _ in range(5):
            loop.submit_audio(b"\x00" * p.INPUT_FRAME_BYTES)
    assert loop.metrics.dropped == 1


def test_a_commit_opens_a_response_and_it_closes_itself():
    frames, sink = collector()
    loop = FrameLoop(SilenceModel(reply_frames=2, reply_text="hello"), sink)
    loop.commit_turn()
    for _ in range(3):
        loop.submit_audio(b"\x00" * p.INPUT_FRAME_BYTES)
    loop.run_pending()
    controls = [f.control for f in frames]
    assert controls[0] == "response_open"
    assert "response_close" in controls
    assert frames[0].text_delta == "hello"


# --- the codec pipeline ------------------------------------------------------


def test_the_decoder_runs_one_frame_behind():
    # The call for frame F submits F and waits on F-1, so the decode hides under
    # the next model step.
    decoder = PipelinedDecoder(lambda tokens: b"pcm:%d" % tokens)
    assert decoder.submit(1) is None
    assert decoder.submit(2) == b"pcm:1"
    assert decoder.submit(3) == b"pcm:2"
    assert decoder.flush() == b"pcm:3"


def test_nothing_is_ever_more_than_one_frame_in_flight():
    # A decoder that can fall behind turns into unbounded queue debt three minutes
    # into a call.
    decoder = PipelinedDecoder(lambda tokens: b"")
    for n in range(50):
        decoder.submit(n)
    assert decoder.in_flight
    decoder.flush()
    assert not decoder.in_flight


def test_the_decoder_serves_a_second_response_after_a_flush():
    """Every test here covered one response. After flush() the pipeline was empty but
    still marked started, so the next response's first frame asked the codec to decode
    None, and a strict codec raised: the session died at the agent's second reply."""
    asked = []

    def decode(tokens):
        asked.append(tokens)
        if tokens is None:
            raise TypeError("cannot decode None")
        return b"pcm:%d" % tokens

    decoder = PipelinedDecoder(decode)
    assert decoder.submit(1) is None
    assert decoder.submit(2) == b"pcm:1"
    assert decoder.flush() == b"pcm:2"

    assert decoder.submit(3) is None, "the second response starts one frame behind too"
    assert decoder.submit(4) == b"pcm:3"
    assert decoder.flush() == b"pcm:4"
    assert None not in asked


def test_flushing_an_empty_pipeline_is_harmless():
    decoder = PipelinedDecoder(lambda tokens: b"")
    assert decoder.flush() is None


def test_silence_is_the_right_length():
    assert len(silence(p.OUTPUT_FRAME_BYTES)) == p.OUTPUT_FRAME_BYTES


def test_pinning_fails_soft_where_there_is_no_affinity_api():
    # A developer laptop is not a broken box. On the box the caller checks the
    # return value, because an unpinned codec worker is a frame-budget problem
    # that presents as a model problem.
    assert pin_to_cores([0]) in (True, False)


# --- choosing a model --------------------------------------------------------


def test_there_is_no_silent_fallback_unless_it_is_asked_for():
    # A server that quietly serves silence when the GPU is missing will do exactly
    # that during a demo, and nobody will notice until the room is quiet. On a
    # laptop this raises; on the box it returns the real model. Never silence.
    try:
        model = build_model(ModelPaths("/nonexistent"))
    except ModelUnavailable:
        return
    assert not isinstance(model, SilenceModel)


def test_the_stand_in_can_be_asked_for_explicitly():
    model = build_model(ModelPaths("/nonexistent"), allow_silence=True)
    assert isinstance(model, SilenceModel)


def test_the_stand_in_refuses_to_run_after_close():
    model = SilenceModel()
    model.close()
    with pytest.raises(RuntimeError):
        model.step(b"")


def test_pinning_can_take_a_thread_of_its_own():
    """The decode wants its own cores; the model step must not be pinned with it. The
    helper only ever pinned the whole process, so there was no way to ask for that."""
    import os

    from zeg.runtime.codec import pin_to_cores

    seen = []

    class FakeOs:
        def __init__(self):
            self.sched_setaffinity = lambda who, cores: seen.append((who, set(cores)))

    real = getattr(os, "sched_setaffinity", None)
    os.sched_setaffinity = FakeOs().sched_setaffinity
    try:
        assert pin_to_cores([5, 6]) is True
        assert pin_to_cores([5, 6], thread_id=4242) is True
    finally:
        if real is None:
            del os.sched_setaffinity
        else:
            os.sched_setaffinity = real
    assert seen == [(0, {5, 6}), (4242, {5, 6})]
