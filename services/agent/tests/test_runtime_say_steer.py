"""Say and steer on the model side of the wire.

The client half and the session half were each tested and each passed, while the
server accepted both messages, stored them, and never handed either to the model. The
disclosure and every briefing reached the box and went no further. These tests go all
the way from a client message to the model, through the real dispatcher.
"""

import inspect
import re

from zeg.runtime import protocol as p
from zeg.runtime import session as session_mod
from zeg.runtime.loop import FrameLoop
from zeg.runtime.model import CudaSpeechModel, ModelUnavailable, SilenceModel
from zeg.runtime.server import RuntimeServer
from zeg.runtime.session import ServerSession

import pytest

SILENT_INPUT = b"\x00" * p.INPUT_FRAME_BYTES


class Recording(SilenceModel):
    """Logs the order the loop called it in."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.log = []

    def step(self, pcm):
        self.log.append("step")
        return super().step(pcm)

    def inject_context(self, text):
        self.log.append("steer")
        super().inject_context(text)

    def speak_text(self, text):
        self.log.append("say")
        super().speak_text(text)

    def cancel_response(self, reason):
        self.log.append("cancel")
        super().cancel_response(reason)


def loop_for(model):
    frames = []
    return FrameLoop(model, frames.append), frames


def step(loop, n=1):
    for _ in range(n):
        loop.submit_audio(SILENT_INPUT)
        loop.run_pending()


# --- the loop reaches the model -------------------------------------------------


def test_a_steer_reaches_the_models_context():
    model = SilenceModel()
    loop, frames = loop_for(model)
    loop.steer("Still no evidence for ownership.")
    loop.run_pending()
    assert model.context == ["Still no evidence for ownership."]


def test_a_steer_is_never_voiced():
    model = SilenceModel()
    loop, frames = loop_for(model)
    loop.steer("Elapsed 5:00. Phase: depth_one.")
    loop.run_pending()
    step(loop, 5)
    assert not [f for f in frames if f.audible or f.text_delta]


def test_a_say_opens_a_response_carrying_the_exact_words():
    model = SilenceModel(reply_frames=3)
    loop, frames = loop_for(model)
    loop.say("This call is recorded. Is that okay?")
    loop.run_pending()
    step(loop, 3)
    assert frames[0].control == "response_open"
    assert frames[0].text_delta == "This call is recorded. Is that okay?"
    assert frames[-1].control == "response_close"


def test_a_say_opens_and_closes_even_with_no_configured_reply():
    """With one frame the close overwrote the open, so the response never started."""
    model = SilenceModel()
    loop, frames = loop_for(model)
    loop.say("Thanks.")
    loop.run_pending()
    step(loop, 3)
    controls = [f.control for f in frames if f.control]
    assert controls == ["response_open", "response_close"]


def test_a_generated_reply_does_not_inherit_an_earlier_fixed_text():
    model = SilenceModel(reply_frames=2, reply_text="generated")
    loop, frames = loop_for(model)
    loop.say("fixed")
    loop.run_pending()
    step(loop, 2)
    loop.commit_turn()
    loop.run_pending()
    step(loop, 2)
    opened = [f.text_delta for f in frames if f.control == "response_open"]
    assert opened == ["fixed", "generated"]


# --- ordering -----------------------------------------------------------------


def test_a_steer_does_not_overtake_the_audio_it_describes():
    model = Recording()
    loop, _ = loop_for(model)
    loop.submit_audio(SILENT_INPUT)
    loop.steer("briefing about what was just said")
    loop.run_pending()
    assert model.log == ["step", "steer"]


def test_a_say_does_not_overtake_the_end_of_the_candidates_turn():
    model = Recording()
    loop, _ = loop_for(model)
    loop.submit_audio(SILENT_INPUT)
    loop.say("Thanks.")
    loop.run_pending()
    assert model.log == ["step", "say"]


def test_a_cancel_still_jumps_ahead_of_a_queued_say():
    model = Recording()
    loop, _ = loop_for(model)
    loop.say("queued")
    loop.cancel("barge_in")
    loop.run_pending()
    assert model.log == ["cancel", "say"]


# --- all the way through the server ---------------------------------------------


def configured():
    s = ServerSession("s1")
    s.on_client(p.Wire().configure("be brief", greeting="hello"))
    s.drain_actions()
    return s


def dispatcher():
    # The dispatcher reads nothing from the server, so it needs no socket or weights.
    return RuntimeServer.__new__(RuntimeServer)


def test_a_client_steer_reaches_the_model_through_the_real_dispatcher():
    session = configured()
    model = SilenceModel()
    loop, _ = loop_for(model)
    session.on_client(p.Wire().steer("Phase: depth_two. Ask for a tradeoff."))
    dispatcher()._dispatch(session, loop)
    loop.run_pending()
    assert model.context == ["Phase: depth_two. Ask for a tradeoff."]


def test_a_client_say_is_voiced_through_the_real_dispatcher():
    session = configured()
    model = SilenceModel(reply_frames=3)
    loop, frames = loop_for(model)
    session.on_client(p.Wire().say("Is that okay?"))
    dispatcher()._dispatch(session, loop)
    loop.run_pending()
    step(loop, 3)
    assert frames[0].text_delta == "Is that okay?"


def test_every_action_the_session_emits_has_a_route_to_the_model():
    """The guard for this whole class of bug. Both halves passed their own tests while
    the join between them dropped two message kinds on the floor."""
    emitted = set(re.findall(r'Action\("(\w+)"', inspect.getsource(session_mod)))
    routed = inspect.getsource(RuntimeServer._dispatch)
    unrouted = sorted(k for k in emitted if '"%s"' % k not in routed)
    assert {"say", "steer"} <= emitted
    assert not unrouted, "the session emits actions the server never routes: %s" % unrouted


# --- the real model -------------------------------------------------------------


def unloaded_cuda_model():
    model = CudaSpeechModel.__new__(CudaSpeechModel)
    model._loaded = False
    return model


def test_the_real_model_refuses_context_before_load_rather_than_dropping_it():
    with pytest.raises(ModelUnavailable):
        unloaded_cuda_model().inject_context("briefing")


def test_the_real_model_refuses_fixed_speech_before_load():
    with pytest.raises(ModelUnavailable):
        unloaded_cuda_model().speak_text("Is that okay?")


def test_both_new_seams_are_marked_for_the_box():
    source = inspect.getsource(CudaSpeechModel)
    assert "SEAM 4" in source and "SEAM 5" in source
