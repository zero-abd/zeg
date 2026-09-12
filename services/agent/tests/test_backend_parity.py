"""Every backend drives the interview, whether or not it can recognise speech.

Some backends report when the candidate stopped talking. Some cannot: a playback
backend speaks a script and hears nothing. The engine needs that boundary either way,
because consent, probing, briefing and rollover all hang off a candidate turn.

The harness supplies the boundary when the backend does not, and counts how often it had
to. A non-zero count is the honest signal that the backend is playback.
"""

import pytest

from zeg.backends import MockBackend
from zeg.conversation import InterviewRunner
from zeg.interview import Interview
from zeg.scoring import score_call


def driven(backend):
    return InterviewRunner(backend, interview=Interview()).run()


def speaking():
    return pytest.importorskip("zeg.backends.tts").TTSBackend()


# --- parity --------------------------------------------------------------------


def test_the_mock_backend_drives_a_whole_interview():
    r = driven(MockBackend())
    assert r.consent is True
    assert r.probes
    assert [t for t in r.transcript if t.speaker == "caller"]


def test_the_speaking_backend_drives_a_whole_interview_too():
    """It was playback: consent was never resolved and no probe was ever issued, while
    the transcript still looked plausible. That is the demo a judge would have seen."""
    r = driven(speaking())
    assert r.consent is True
    assert r.probes
    assert [t for t in r.transcript if t.speaker == "caller"]


def test_both_backends_reach_the_same_consent_and_probe_count():
    a, b = driven(MockBackend()), driven(speaking())
    assert a.consent == b.consent
    assert len(a.probes) == len(b.probes)


def test_both_backends_produce_a_scoreable_transcript():
    for backend in (MockBackend(), speaking()):
        assert score_call(driven(backend).transcript).overall is not None


# --- honesty about which is which -------------------------------------------------


def test_a_backend_that_reports_its_own_turns_needs_no_help():
    assert driven(MockBackend()).synthesised_turns == 0


def test_a_playback_backend_is_counted_as_needing_help():
    """The count is the signal. It says the audio is real and the listening is not."""
    r = driven(speaking())
    assert r.synthesised_turns == len([t for t in r.transcript if t.speaker == "caller"])


def test_the_speaking_backend_still_satisfies_the_session_contract():
    s = speaking().start_session("sys")
    s.steer("a briefing")
    s.say("a fixed sentence")
    s.close()
