"""Which backends actually drive the interview engine.

Not every backend is interchangeable from the engine's point of view. One of them is
playback: it speaks a fixed script and never reports that the candidate said anything,
so nothing downstream of a candidate turn ever happens. That is a legitimate thing for a
demo to be, and it is a dangerous thing to mistake for a real call.

These tests state the difference so nobody has to discover it in front of an audience.
"""

import pytest

from zeg.backends import MockBackend
from zeg.conversation import InterviewRunner
from zeg.interview import Interview


def driven(backend):
    return InterviewRunner(backend, interview=Interview()).run()


def test_the_mock_backend_drives_a_whole_interview():
    r = driven(MockBackend())
    assert r.consent is True
    assert r.probes, "probes require the engine to see candidate turns"
    assert [t for t in r.transcript if t.speaker == "caller"]


def test_the_speaking_backend_is_playback_and_the_engine_knows_nothing():
    """It never reports candidate speech, so consent is never resolved, no probe is
    issued and no rollover can fire. Good for a canned demo. Not a screening call, and
    not evidence that consent was taken."""
    tts = pytest.importorskip("zeg.backends.tts")
    r = driven(tts.TTSBackend())

    assert r.consent is None, "playback cannot take consent"
    assert not r.probes
    assert not [t for t in r.transcript if t.speaker == "caller"]


def test_the_speaking_backend_still_satisfies_the_session_contract():
    """Whatever it does with audio, it has to accept steering, or a future change that
    routes the engine through it will fail at the worst moment."""
    tts = pytest.importorskip("zeg.backends.tts")
    s = tts.TTSBackend().start_session("sys")
    s.steer("a briefing")
    s.say("a fixed sentence")
    s.close()
