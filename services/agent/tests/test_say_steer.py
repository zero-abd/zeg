"""The two ways the interview layer steers a model that cannot remember.

`say` is for wording that is ours and not the model's: the disclosure, the consent
request, the wrap-up. `steer` is context the candidate never hears. They are separate
because they fail differently, and the tests below pin both failure modes.
"""

import pytest

from zeg.audio import AudioFrame, tone
from zeg.backends import AgentAudio, AgentText, MockBackend
from zeg.config import AudioConfig
from zeg.runtime import protocol as p
from zeg.runtime.session import ServerSession


@pytest.fixture
def audio():
    return AudioConfig()


def drive(session, audio, n, speaking=False):
    out = []
    for _ in range(n):
        f = (tone(audio.input_sample_rate, audio.input_frame_samples, amplitude=0.3)
             if speaking else
             AudioFrame.silence(audio.input_sample_rate, audio.input_frame_samples))
        session.push_audio(f)
        out.extend(session.poll())
    return out


# --- the mock ----------------------------------------------------------------


def test_say_speaks_the_exact_words(audio):
    s = MockBackend(audio).start_session("sys")
    s.say("This call is recorded. Is that okay?")
    events = drive(s, audio, 20)
    said = [e.text for e in events if isinstance(e, AgentText) and e.final]
    assert "This call is recorded. Is that okay?" in said


def test_say_produces_audio(audio):
    s = MockBackend(audio).start_session("sys")
    s.say("hello there")
    assert [e for e in drive(s, audio, 20) if isinstance(e, AgentAudio)]


def test_steer_never_reaches_the_speaker(audio):
    """A steer that gets spoken reads the agent its own notes aloud."""
    s = MockBackend(audio).start_session("sys")
    s.steer("Elapsed 3:00. Still no evidence for ownership.")
    events = drive(s, audio, 20)
    assert not [e for e in events if isinstance(e, AgentAudio)]
    assert not [e for e in events if isinstance(e, AgentText)]


def test_steer_is_recorded_so_it_can_be_asserted_on(audio):
    s = MockBackend(audio).start_session("sys")
    s.steer("brief one")
    s.steer("brief two")
    assert s.steers == ["brief one", "brief two"]


def test_say_replaces_whatever_was_queued(audio):
    """The caller asked for this utterance now, not behind a half-finished one."""
    s = MockBackend(audio).start_session("sys", greeting="a long greeting that runs on")
    drive(s, audio, 3)
    s.say("Time is up.")
    said = [e.text for e in drive(s, audio, 40) if isinstance(e, AgentText) and e.final]
    assert said[-1] == "Time is up."


def test_both_reject_a_closed_session(audio):
    s = MockBackend(audio).start_session("sys")
    s.close()
    with pytest.raises(RuntimeError):
        s.say("anything")
    with pytest.raises(RuntimeError):
        s.steer("anything")


# --- the server side ----------------------------------------------------------


def configured():
    s = ServerSession("s1")
    s.on_client(p.Wire().configure("be brief", greeting="hello"))
    s.drain_actions()
    return s


def errors(out):
    return [m for m in out if "error" in m.get("type", "") or "code" in m]


def test_the_server_queues_a_say(_=None):
    s = configured()
    assert s.on_client(p.Wire().say("Is that okay?")) == []
    assert s.pending_say == "Is that okay?"


def test_the_server_queues_steers_in_order(_=None):
    s = configured()
    s.on_client(p.Wire().steer("one"))
    s.on_client(p.Wire().steer("two"))
    assert s.take_steers() == ["one", "two"]


def test_draining_steers_empties_the_queue(_=None):
    s = configured()
    s.on_client(p.Wire().steer("one"))
    s.take_steers()
    assert s.take_steers() == []


def test_empty_text_is_rejected_on_both(_=None):
    s = configured()
    assert errors(s.on_client(p.Wire().say("   ")))
    assert errors(s.on_client(p.Wire().steer("")))


def test_say_is_refused_while_the_candidate_is_talking(_=None):
    """Speaking over someone is the failure they remember."""
    s = configured()
    s.on_client(p.Wire().turn_start(1))
    assert errors(s.on_client(p.Wire().say("interrupting")))
    assert s.pending_say is None


def test_steer_is_allowed_mid_turn(_=None):
    """Context is not audible, so there is no reason to wait for a boundary."""
    s = configured()
    s.on_client(p.Wire().turn_start(1))
    assert s.on_client(p.Wire().steer("still no evidence for ownership")) == []
