"""One contract, every backend.

The backends were kept in step by tests copied from one file to another, and the
copies drifted. say and steer were added to the mock with tests and to the real backend
without them, and on the real backend both crashed on every call. Every rule here runs
against every backend, and a guard fails if the contract gains a method no rule here
exercises.
"""

import inspect
import sys

import pytest

from fakes import FakeLink, agent_frame
from zeg.audio import AudioFrame
from zeg.backends import AgentAudio, AgentText, MockBackend, VoiceSession
from zeg.backends.gb10 import GB10Backend, GB10Session
from zeg.config import AudioConfig, BackendConfig

AUDIO = AudioConfig()


@pytest.fixture(scope="module")
def speaking_backend():
    return pytest.importorskip("zeg.backends.tts").TTSBackend()


def _mock(request):
    return MockBackend()


def _real(request):
    return GB10Backend(BackendConfig(kind="gb10"), link_factory=FakeLink)


def _speaking(request):
    return request.getfixturevalue("speaking_backend")


@pytest.fixture(params=[_mock, _real, _speaking], ids=["mock", "real", "speaking"])
def session(request):
    s = request.param(request).start_session("be brief")
    yield s
    s.close()


def silence():
    return AudioFrame.silence(AUDIO.input_sample_rate, AUDIO.input_frame_samples)


def queue_an_event(session):
    """Leave at least one event waiting, without polling for it."""
    if isinstance(session, GB10Session):
        link = session._link
        link.deliver(link.wire.response_started("r1", "t1"))
        link.deliver(agent_frame(link))
        session.push_audio(silence())
        session.say("That is my time.")  # over a speaking agent, so it queues an interrupt
        return
    # The mock and the speaking backend both stream a fixed line a few frames after
    # being asked for it. Caller speech would not do: the speaking backend is playback
    # and cannot hear, so speech followed by silence queues nothing there at all.
    session.say("That is my time.")
    for _ in range(10):
        session.push_audio(silence())


# --- closing --------------------------------------------------------------------


def test_close_is_safe_to_call_twice(session):
    session.close()
    session.close()


def test_audio_is_refused_after_close(session):
    session.close()
    with pytest.raises(RuntimeError):
        session.push_audio(silence())


def test_say_is_refused_after_close(session):
    session.close()
    with pytest.raises(RuntimeError):
        session.say("anything")


def test_steer_is_refused_after_close(session):
    session.close()
    with pytest.raises(RuntimeError):
        session.steer("anything")


def test_closing_discards_whatever_was_still_queued(session):
    """The caller has stopped listening. During a rollover the runner closes the old
    session while still reading it, and anything left queued there describes speech
    the candidate will never hear. A session that ends itself is different: it keeps
    its final error so the caller can learn why, and the real backend's own tests
    cover that."""
    queue_an_event(session)
    assert session._pending, "nothing was queued, so this would prove nothing"
    session.close()
    assert list(session.poll()) == []


# --- steering -------------------------------------------------------------------


def test_a_steer_is_never_voiced(session):
    session.steer("Elapsed 5:00. Still no evidence for ownership.")
    for _ in range(20):
        session.push_audio(silence())
    events = list(session.poll())
    assert not [e for e in events if isinstance(e, (AgentAudio, AgentText))]


# --- the guard ------------------------------------------------------------------


def test_every_method_the_contract_requires_is_exercised_here():
    required = sorted(VoiceSession.__abstractmethods__)
    source = inspect.getsource(sys.modules[__name__])
    untested = [m for m in required if ".%s(" % m not in source]
    assert not untested, "the contract requires methods no rule here calls: %s" % untested
