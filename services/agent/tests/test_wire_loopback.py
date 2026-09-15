"""The real client talking to the real server, over the real protocol, in memory.

Both halves were built against the same protocol and tested against their own fakes:
the client against a fake connection that answered whatever the test told it to, the
server against messages the test built by hand. Nothing had ever passed one half's
actual output to the other. These tests do, serialising every message both ways.
"""

from fakes import LoopbackLink
from zeg.audio import AudioFrame, tone
from zeg.backends import AgentAudio, AgentInterrupted, AgentText, BackendError
from zeg.backends.gb10 import GB10Config, GB10Session
from zeg.config import AudioConfig
from zeg.runtime import protocol as p
from zeg.runtime.model import SilenceModel

AUDIO = AudioConfig()
ENDPOINT_FRAMES = GB10Config().endpoint_silence_ms // AUDIO.frame_ms + 4


def connect(model=None):
    link = LoopbackLink(model)
    return GB10Session(link, "be brief", audio=AUDIO), link


def push(session, n, speaking=False):
    events = []
    for _ in range(n):
        if session.closed:
            break
        frame = (
            tone(AUDIO.input_sample_rate, AUDIO.input_frame_samples, amplitude=0.3)
            if speaking
            else AudioFrame.silence(AUDIO.input_sample_rate, AUDIO.input_frame_samples)
        )
        session.push_audio(frame)
        events.extend(session.poll())
    return events


def assert_clean(link, events=()):
    assert not link.errors(), "the server rejected something: %s" % link.errors()
    assert not [e for e in events if isinstance(e, BackendError)], events


def finals(events):
    return [e.text for e in events if isinstance(e, AgentText) and e.final]


# --- the handshake -------------------------------------------------------------


def test_the_client_is_configured_by_the_real_server():
    session, link = connect()
    assert link.sent[0]["type"] == p.CONFIGURE
    assert link.server.configured
    assert link.server.instructions == "be brief"
    assert session._configured
    assert_clean(link)


# --- audio and turns ------------------------------------------------------------


def test_caller_audio_reaches_the_model_as_whole_frames():
    session, link = connect()
    push(session, 8)  # 8 transport frames of 20 ms are 2 model frames of 80 ms
    assert link.loop.metrics.frames == 2
    assert_clean(link)


def test_a_whole_turn_gets_a_reply_the_client_can_hear():
    session, link = connect(SilenceModel(reply_frames=6, reply_text="Tell me about a bug."))
    events = push(session, 20, speaking=True)
    events += push(session, ENDPOINT_FRAMES + 40)
    types = link.received_types()
    assert p.TURN_STARTED in types and p.TURN_COMMITTED in types
    assert p.RESPONSE_STARTED in types and p.RESPONSE_DONE in types
    assert "Tell me about a bug." in finals(events)
    assert [e for e in events if isinstance(e, AgentAudio)]
    assert_clean(link, events)


# --- steering the model over the wire ---------------------------------------------


def test_a_steer_reaches_the_models_context_over_the_wire():
    model = SilenceModel()
    session, link = connect(model)
    session.steer("Phase: depth_two. Still no evidence for tradeoffs.")
    push(session, 4)
    assert model.context == ["Phase: depth_two. Still no evidence for tradeoffs."]
    assert_clean(link)


def test_a_say_comes_back_to_the_client_word_for_word():
    session, link = connect(SilenceModel(reply_frames=3))
    session.say("This call is recorded. Is that okay?")
    events = push(session, 40)
    assert "This call is recorded. Is that okay?" in finals(events)
    assert [e for e in events if isinstance(e, AgentAudio)]
    assert_clean(link, events)


# --- barge-in -------------------------------------------------------------------


def test_barge_in_stops_the_reply_on_both_sides_then_the_agent_answers_it():
    session, link = connect(SilenceModel(reply_frames=200, reply_text="A long question."))
    push(session, 20, speaking=True)
    push(session, ENDPOINT_FRAMES + 12)
    assert link.server._response_id is not None, "the reply never started, nothing to cut"

    events = push(session, 12, speaking=True)
    assert [e for e in events if isinstance(e, AgentInterrupted)]
    assert [m for m in link.sent if m["type"] == p.CANCEL], "the client never told the server"
    assert link.server._response_id is None, "the server still thinks the agent is talking"

    # Short of the endpoint, the candidate is still mid-interruption. The cancelled
    # reply has to stay silent.
    quiet = push(session, ENDPOINT_FRAMES - 10)
    assert not [e for e in quiet if isinstance(e, AgentAudio)]

    # Once they stop, the agent answers what they said. Audio now belongs to that new
    # reply, not to the cancelled one coming back. An earlier version of this test
    # asserted no audio at all after a barge-in, which is wrong: it failed on exactly
    # this correct behaviour.
    reply = push(session, 40)
    assert link.received_types().count(p.RESPONSE_STARTED) == 2
    assert [e for e in reply if isinstance(e, AgentAudio)]
    assert_clean(link, events + quiet + reply)


# --- closing --------------------------------------------------------------------


def test_closing_ends_the_server_session_without_an_error():
    session, link = connect()
    push(session, 8)
    events = list(session.poll())
    session.close()
    assert link.server.closed
    assert_clean(link, events)


# --- words the recogniser confirms while it settles ---------------------------------


def finals_of(events):
    from zeg.backends import UserTranscript

    return [e.text for e in events if isinstance(e, UserTranscript) and e.final]


def test_a_one_word_answer_confirmed_while_settling_reaches_the_client():
    """The server sent the final transcript at the commit and dropped what the recogniser
    confirmed while it settled. A candidate who answered "yes" produced an empty final,
    the client discarded it, and consent could never have been taken."""
    from fakes import SettlingRecogniser

    session, link = connect(SettlingRecogniser(["yes"]))
    events = push(session, 40, speaking=True) + push(session, 60)
    assert finals_of(events) == ["yes"]
    assert_clean(link, events)


def test_the_last_word_confirmed_while_settling_is_not_dropped():
    from fakes import SettlingRecogniser

    session, link = connect(SettlingRecogniser(["yes", "that", "is", "fine"]))
    events = push(session, 40, speaking=True) + push(session, 60)
    assert finals_of(events) == ["yes that is fine"]
    assert_clean(link, events)


def test_the_answer_reaches_the_client_before_the_reply_starts():
    """The interview decides what to say when it hears the answer, so the answer has to
    arrive before the agent starts replying to it."""
    from fakes import SettlingRecogniser

    session, link = connect(SettlingRecogniser(["yes"], reply_frames=6))
    push(session, 40, speaking=True)
    push(session, 60)
    kinds = [m["type"] for m in link.received if m["type"] in (p.TRANSCRIPT_FINAL, p.RESPONSE_STARTED)]
    assert p.TRANSCRIPT_FINAL in kinds and p.RESPONSE_STARTED in kinds
    assert kinds.index(p.TRANSCRIPT_FINAL) < kinds.index(p.RESPONSE_STARTED)


def test_a_model_that_never_replies_still_finalises_the_answer():
    from fakes import SettlingRecogniser

    session, link = connect(SettlingRecogniser(["yes"], never_reply=True))
    events = push(session, 40, speaking=True) + push(session, 200)
    assert finals_of(events) == ["yes"]
    assert_clean(link, events)
