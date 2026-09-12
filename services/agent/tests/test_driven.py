"""The engine driving a real backend session.

These are the integration tests. The unit tests prove each part behaves; these prove
the parts agree with each other, which is where the last two real bugs were hiding.
"""

import pytest

from zeg.backends import MockBackend
from zeg.config import CallConfig
from zeg.conversation import CallerTurn, InterviewRunner
from zeg.interview import Interview
from zeg.memory import RolloverPolicy
from zeg.scoring import score_call


def run(caller=None, **kw):
    iv = Interview(**kw) if kw else Interview()
    r = InterviewRunner(MockBackend(), interview=iv)
    return r.run(caller) if caller else r.run()


#: Every caller script needs this first: the interview will not proceed without a
#: clear yes, and "not a clear yes" includes an answer about something else entirely.
CONSENT = CallerTurn("yes that is fine", speak_s=1.5)


def agent_turns(result):
    return [t.text for t in result.transcript if t.speaker == "agent"]


def caller_turns(result):
    return [t.text for t in result.transcript if t.speaker == "caller"]


# --- the two integration bugs, pinned ----------------------------------------


def test_the_greeting_appears_once(_=None):
    """A backend echoes back what it spoke. Recording the echo as well put the
    disclosure in the transcript twice."""
    turns = agent_turns(run())
    greetings = [t for t in turns if "AI interviewer" in t]
    assert len(greetings) == 1


def test_the_callers_own_words_reach_the_transcript(_=None):
    """The endpoint fires during the silence after speech, not during it, so the
    utterance has to outlive the frames that carried it."""
    said = caller_turns(run())
    assert "a race condition in our payment reconciler" in said
    assert not any("word word" in t for t in said)


# --- the engine is actually in charge -----------------------------------------


def test_consent_is_taken_before_anything_substantive(_=None):
    r = run()
    assert r.consent is True
    assert "AI interviewer" in r.transcript[0].text
    assert r.transcript[1].speaker == "caller"


def test_a_refusal_ends_the_call_and_nothing_more_is_asked(_=None):
    refuse = [CallerTurn("no, I'd rather not", speak_s=1.5),
              CallerTurn("tell me about a bug anyway", speak_s=3.0)]
    r = run(refuse)
    assert r.consent is False
    assert r.ended == "consent declined"
    assert len(caller_turns(r)) == 1


def test_probes_are_issued_as_the_interview_descends(_=None):
    r = run()
    assert len(r.probes) >= 3
    assert any("personally did" in p for p in r.probes)
    assert any("number" in p for p in r.probes)


def test_the_model_is_briefed_at_least_once(_=None):
    assert run().steers


def test_briefings_are_never_spoken(_=None):
    """A steer that reaches the speaker reads the agent its own notes aloud."""
    spoken = " ".join(agent_turns(run()))
    assert "Elapsed" not in spoken
    assert "Still no evidence" not in spoken


# --- rollover in a driven call ------------------------------------------------


def test_a_long_call_rolls_the_session_without_dropping_the_thread(_=None):
    slow = [CONSENT] + [CallerTurn("we rewrote the payment reconciler after an outage",
                                   speak_s=8.0, pause_after_s=2.0)] * 8
    r = run(slow, rollover=RolloverPolicy(context_horizon_s=20, min_session_s=10))
    assert r.rollovers >= 1
    assert r.ended is None, "a rollover must not end the call"
    assert len(caller_turns(r)) == len(slow)


def test_a_short_call_does_not_roll(_=None):
    assert run().rollovers == 0


# --- the whole path -----------------------------------------------------------


def test_the_call_produces_a_scoreable_transcript(_=None):
    a = score_call(run().transcript)
    assert a.overall is not None
    assert a.band != "insufficient signal"


def test_every_score_in_a_driven_call_carries_a_quote(_=None):
    for d in score_call(run().transcript).dimensions:
        assert d.insufficient or d.evidence


def test_a_declined_call_cannot_be_scored(_=None):
    refuse = [CallerTurn("no thank you", speak_s=1.5)]
    assert score_call(run(refuse).transcript).band == "insufficient signal"


def test_the_wall_clock_still_ends_a_runaway_call(_=None):
    long = [CONSENT] + [CallerTurn("still going", speak_s=20.0, pause_after_s=1.0)] * 10
    r = run(long, call=CallConfig(max_duration_s=60, wrap_up_at_s=45))
    assert r.ended == "time limit reached"
    assert r.duration_s <= 90
