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


# --- turn taking ---------------------------------------------------------------


POLITE = [CONSENT] + [
    CallerTurn("a race condition in our payment reconciler", speak_s=4.0),
    CallerTurn("i wrote the advisory-lock fix myself", speak_s=3.5),
    CallerTurn("about twelve hundred a second before, forty thousand after", speak_s=4.5),
]


def test_a_caller_who_waits_is_never_treated_as_interrupting(_=None):
    """The bug this pins: draining on the transcript returned while seconds of speech
    were still queued, so a polite caller talked over every single turn."""
    assert run(POLITE).interruptions == 0


def test_the_default_script_exercises_one_deliberate_barge_in(_=None):
    assert run().interruptions == 1


def test_the_agent_is_allowed_to_finish_its_turn(_=None):
    """A 40-word disclosure takes time to say. The call has to be long enough to
    contain it, or the audio was cut off rather than played."""
    assert run(POLITE).duration_s > 40


def test_a_caller_who_cuts_in_does_interrupt(_=None):
    cut_in = [CONSENT, CallerTurn("actually can I ask something", speak_s=3.0,
                                  barge_in=True)]
    assert run(cut_in).interruptions >= 1


def test_an_interruption_does_not_lose_the_callers_turn(_=None):
    cut_in = [CONSENT, CallerTurn("we rewrote the reconciler", speak_s=3.0,
                                  barge_in=True)]
    assert "we rewrote the reconciler" in caller_turns(run(cut_in))


def test_the_agent_speaks_at_all(_=None):
    assert run().agent_audio_frames > 0


# --- rollover on a box that runs one conversation at a time --------------------


class OneAtATime(MockBackend):
    """Enforces what the real backend and the server both enforce: one live session.

    The plain mock allows two at once, which is how a rollover that opened the new
    session before closing the old one passed every test and would have crashed the
    first long call on the box.
    """

    def __init__(self):
        super().__init__()
        self.live = None
        self.sessions = []

    def start_session(self, system_prompt, greeting=None):
        if self.live is not None and not self.live._closed:
            raise RuntimeError("a conversation is already in progress")
        session = super().start_session(system_prompt, greeting=greeting)
        self.live = session
        self.sessions.append(session)
        return session


def long_call_on(backend):
    slow = [CONSENT] + [CallerTurn("we rewrote the payment reconciler after an outage",
                                   speak_s=8.0, pause_after_s=2.0)] * 8
    iv = Interview(rollover=RolloverPolicy(context_horizon_s=20, min_session_s=10))
    return InterviewRunner(backend, interview=iv).run(slow), len(slow)


def test_rollover_works_when_only_one_session_may_be_live():
    backend = OneAtATime()
    r, turns = long_call_on(backend)
    assert r.rollovers >= 1
    assert r.ended is None
    assert len(caller_turns(r)) == turns
    assert len(backend.sessions) == r.rollovers + 1


def test_the_old_session_is_closed_before_the_new_one_opens():
    backend = OneAtATime()
    long_call_on(backend)
    assert all(s._closed for s in backend.sessions[:-1])


def test_a_rolled_session_is_steered_with_the_last_exchange():
    """The briefing alone makes the new session start over. The last exchange is what
    lets it continue the thread the candidate is in the middle of."""
    backend = OneAtATime()
    r, _ = long_call_on(backend)
    seeded = backend.sessions[1].steers[0]
    assert "Where we are:" in seeded
    assert "The last thing said" in seeded
    assert "Candidate:" in seeded


def test_a_rolled_session_is_not_sent_its_system_prompt_twice():
    backend = OneAtATime()
    long_call_on(backend)
    prompt = Interview().system_prompt.strip().splitlines()[0]
    assert prompt not in backend.sessions[1].steers[0]


# --- a replaced session stops being read ---------------------------------------


class _OldSession:
    """A session whose queue was snapshotted before the swap, as the mock's is."""

    def __init__(self, events):
        self._events = events
        self.closed = False

    def poll(self):
        for ev in list(self._events):
            yield ev

    def close(self):
        self.closed = True


class _Stub:
    """An interview that answers the first event with one action, then records."""

    def __init__(self, first_action):
        self.first_action = first_action
        self.seen = []

    def on_event(self, ev, t_s):
        self.seen.append(ev)
        return [self.first_action] if len(self.seen) == 1 else []


def _consume_once(stub, events):
    from zeg.backends import AgentText, UserTranscript  # noqa: F401
    from zeg.conversation import DrivenResult, _VirtualClock
    from zeg.interview import EndCall, Rollover

    runner = InterviewRunner(MockBackend(), interview=stub)
    runner._session = _OldSession(events)
    runner._saying = "we rewrote the reconciler"
    result = DrivenResult()

    def perform(actions):
        for a in actions:
            if isinstance(a, Rollover):
                result.rollovers += 1
                runner._roll(a.seed)
            elif isinstance(a, EndCall):
                result.ended = a.reason

    runner._consume(_VirtualClock(runner.audio.frame_ms), result, perform)
    return result


def test_events_queued_after_a_rollover_never_reach_the_interview():
    """A backend that snapshots its queue kept delivering the old session's events
    after the swap. Those are words from a model that was just closed, which nobody
    heard, and they would have been recorded and scored."""
    from zeg.backends import AgentText, UserTranscript
    from zeg.interview import Rollover
    from zeg.memory import SessionSeed

    stub = _Stub(Rollover(SessionSeed("rules", "Phase: depth_two.")))
    result = _consume_once(stub, [
        UserTranscript("placeholder", final=True),
        AgentText("a question the old model started and nobody heard", final=True),
    ])
    assert result.rollovers == 1
    assert len(stub.seen) == 1


def test_events_queued_after_the_call_ends_never_reach_the_interview():
    from zeg.backends import AgentText, UserTranscript
    from zeg.interview import EndCall

    stub = _Stub(EndCall("consent declined"))
    result = _consume_once(stub, [
        UserTranscript("placeholder", final=True),
        AgentText("anything after the end", final=True),
    ])
    assert result.ended == "consent declined"
    assert len(stub.seen) == 1


# --- backend errors ----------------------------------------------------------------


def test_a_fatal_backend_error_ends_the_call_and_stops_reading():
    from zeg.backends import AgentText, BackendError

    stub = _Stub(None)
    result = _consume_once(stub, [
        BackendError("the speech runtime closed the session", fatal=True),
        AgentText("anything after the failure", final=True),
    ])
    assert result.failed
    assert result.ended.startswith("backend failed")
    assert result.errors == ["the speech runtime closed the session"]
    assert stub.seen == []


def test_a_non_fatal_backend_error_is_recorded_and_the_call_goes_on():
    from zeg.backends import AgentText, BackendError

    stub = _Stub(None)
    result = _consume_once(stub, [
        BackendError("bad agent audio", fatal=False),
        AgentText("still here", final=True),
    ])
    assert not result.failed
    assert result.ended is None
    assert result.errors == ["bad agent audio"]
    assert len(stub.seen) == 1
