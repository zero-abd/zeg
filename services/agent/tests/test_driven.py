"""The engine driving a real backend session.

These are the integration tests. The unit tests prove each part behaves; these prove
the parts agree with each other, which is where the last two real bugs were hiding.
"""

import pytest

from zeg.audio import AudioFrame, tone
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


# --- the clock runs when nobody is talking ----------------------------------------------


def test_the_interview_ends_at_the_limit_with_nothing_said():
    from zeg.interview import EndCall

    from zeg.interview import GOODBYE_LEAD_S, Speak
    from zeg.prompts import TIME_UP

    iv = consented_interview()
    iv.tick(850)  # the wrap-up, said once
    assert iv.tick(900 - GOODBYE_LEAD_S - 0.1) == []
    # The goodbye starts early enough to have played by the limit. The call used to drop
    # at the limit with nothing said.
    actions = iv.tick(900 - GOODBYE_LEAD_S)
    assert [type(a) for a in actions] == [Speak, EndCall]
    assert actions[0].text == TIME_UP
    assert iv.record.ended == "time limit reached"
    assert iv.tick(901) == []


def test_a_call_that_never_became_an_interview_ends_at_the_limit_without_a_goodbye():
    from zeg.backends.base import AgentAudio
    from zeg.interview import EndCall as End

    iv = Interview()
    iv.start()
    iv.on_event(AgentAudio(AudioFrame.silence(22050, 1764)), 899.0)  # kept from timing out
    actions = iv.tick(900)
    assert [type(a) for a in actions] == [End]


def test_the_goodbye_replaces_an_answer_cut_off_by_the_limit():
    """A candidate asking their own closing question at the limit was hung up on."""
    from zeg.backends.base import UserTranscript
    from zeg.interview import Speak
    from zeg.prompts import TIME_UP

    iv = consented_interview()
    actions = iv.on_event(UserTranscript("so what is the team like?", final=True), 897)
    assert [a.text for a in actions if isinstance(a, Speak)] == [TIME_UP]


def wrapped_up_interview():
    from zeg.backends.base import AgentAudio

    iv = consented_interview()
    iv.on_event(AgentAudio(AudioFrame.silence(22050, 1764)), 809.0)
    iv.tick(812)  # the wrap-up, once both sides are quiet
    assert iv.record.wrapped_up_s == 812
    return iv


@pytest.mark.parametrize("text", ["no, I think I'm good, thanks", "nope", "that's all from me"])
def test_a_candidate_with_no_questions_is_thanked_and_the_call_ends(text):
    """The call went on, silent and recorded, for 76 seconds until the time limit."""
    from zeg.backends.base import UserTranscript
    from zeg.interview import EndCall, Speak
    from zeg.prompts import CLOSING

    iv = wrapped_up_interview()
    actions = iv.on_event(UserTranscript(text, final=True), 820)
    assert [a.text for a in actions if isinstance(a, Speak)] == [CLOSING]
    assert [a.reason for a in actions if isinstance(a, EndCall)] == ["completed"]
    assert not any(text in c.text for c in iv.engine.state.claims)


@pytest.mark.parametrize("text", ["no, but what is the team like?", "I'm good at Go, is that used here?"])
def test_a_question_at_the_wrap_up_does_not_end_the_call(text):
    from zeg.backends.base import UserTranscript

    iv = wrapped_up_interview()
    iv.on_event(UserTranscript(text, final=True), 820)
    assert not iv.record.ended


def test_what_the_candidate_says_after_the_wrap_up_is_not_a_claim():
    from zeg.backends.base import UserTranscript

    iv = wrapped_up_interview()
    before = len(iv.engine.state.claims)
    iv.on_event(UserTranscript("I'd love to hear more about how on-call works for the team",
                               final=True), 820)
    iv.on_event(UserTranscript("okay great, that sounds really reasonable to me", final=True), 840)
    assert len(iv.engine.state.claims) == before
    assert "on-call" not in iv.engine.briefing(850)


def test_a_bare_no_ends_the_call_only_as_the_answer_to_the_wrap_up():
    from zeg.backends.base import AgentText, UserTranscript

    iv = wrapped_up_interview()
    iv.on_event(UserTranscript("what are the next steps?", final=True), 820)
    iv.on_event(AgentText("A recruiter will reach out this week. Does that help?", final=True), 830)
    iv.on_event(UserTranscript("no", final=True), 835)
    assert not iv.record.ended


def test_the_candidates_last_words_are_kept_when_the_goodbye_starts():
    """Starting the goodbye early made the limit a window, and what the candidate said in
    it was missing from the transcript."""
    from zeg.backends.base import UserTranscript

    iv = consented_interview()
    iv.on_event(UserTranscript("we cut p99 latency to 30 ms by sharding", final=True), 895)
    assert "we cut p99 latency to 30 ms by sharding" in [
        t.text for t in iv.record.transcript if t.speaker == "caller"
    ]


@pytest.mark.parametrize("text, reason, flag", [
    ("actually, can you stop the recording?", "consent withdrawn", "asked to stop"),
    ("I'd rather speak to a person", "human requested", "speak to a person"),
])
def test_a_request_to_stop_near_the_limit_is_still_on_the_record(text, reason, flag):
    """Both ended the call as a time limit and left no flag, so nobody was told the
    recording might not be usable or that a person had been asked for."""
    from zeg.backends.base import UserTranscript
    from zeg.interview import Speak
    from zeg.prompts import CONSENT_WITHDRAWN, HUMAN_REQUESTED

    iv = consented_interview()
    actions = iv.on_event(UserTranscript(text, final=True), 896)
    assert iv.record.ended == reason
    assert any(flag in f for f in iv.record.flags)
    line = CONSENT_WITHDRAWN if reason == "consent withdrawn" else HUMAN_REQUESTED
    assert [a.text for a in actions if isinstance(a, Speak)] == [line]


def test_a_prohibited_question_near_the_limit_is_flagged():
    from zeg.backends.base import AgentText

    iv = consented_interview()
    iv.on_event(AgentText("How old are you, by the way?", final=True), 896)
    assert any("prohibited question" in f for f in iv.record.flags)
    assert iv.record.ended == "time limit reached"


def test_a_silent_candidate_cannot_hold_the_call_past_the_limit():
    """The limit was only checked when an event arrived. With the candidate silent and
    the agent done, no events came, and this call ran to 1029 seconds."""
    caller = [CONSENT, CallerTurn("we rewrote the payment reconciler after an outage",
                                  speak_s=4.0, pause_after_s=1000.0)]
    r = run(caller)
    assert r.ended == "time limit reached"
    assert r.duration_s <= 901


def consented_interview():
    from zeg.backends.base import UserTranscript

    iv = Interview()
    iv.start()
    iv.on_event(UserTranscript("yes that is fine", final=True), 5)
    return iv


def test_the_clock_delivers_the_wrap_up_once_both_sides_are_quiet():
    from zeg.backends.base import AgentAudio
    from zeg.interview import Speak
    from zeg.prompts import WRAP_UP

    iv = consented_interview()
    iv.on_event(AgentAudio(AudioFrame.silence(22050, 1764)), 810.5)
    assert iv.tick(811.0) == [], "the agent was speaking half a second ago"
    actions = iv.tick(812.6)
    assert [a.text for a in actions if isinstance(a, Speak)] == [WRAP_UP]
    assert iv.record.wrapped_up_s == 812.6
    assert iv.tick(820) == [], "said once"


def test_the_clock_does_not_wrap_up_before_consent_or_before_time():
    from zeg.backends.base import AgentAudio

    iv = Interview()
    iv.start()
    from zeg.prompts import WRAP_UP

    iv.on_event(AgentAudio(AudioFrame.silence(22050, 1764)), 840.0)
    # Asserted as "no wrap-up" rather than "nothing at all": the consent question is now
    # repeated once into silence, and this state, consent still unsettled at 14 minutes,
    # only exists because the test drives the clock straight there.
    assert WRAP_UP not in [getattr(a, "text", "") for a in iv.tick(850)]
    assert iv.record.wrapped_up_s is None
    assert consented_interview().tick(700) == []


def test_a_silent_candidate_hears_the_wrap_up_before_the_call_ends():
    """The wrap-up waited for a caller turn, so a silent candidate reached the limit
    without being told the interview was closing."""
    from zeg.prompts import WRAP_UP

    caller = [CONSENT, CallerTurn("we rewrote the payment reconciler after an outage",
                                  speak_s=4.0, pause_after_s=1000.0)]
    r = run(caller)
    wrap = [t for t in r.transcript if t.speaker == "agent" and t.text == WRAP_UP]
    assert len(wrap) == 1
    assert 810 <= wrap[0].at_s < 900
    assert r.wrapped_up_s == wrap[0].at_s
    assert r.ended == "time limit reached"


# --- no answer to the consent question ---------------------------------------------------


def test_an_unanswered_consent_question_ends_the_call_after_a_quiet_wait():
    """Updated when the question began being repeated once: the wait now runs from the
    repeat, so the call ends later than it used to."""
    from zeg.backends.base import AgentAudio
    from zeg.interview import EndCall, Speak
    from zeg.prompts import CONSENT_REASK, CONSENT_UNANSWERED

    iv = Interview()
    iv.start()
    iv.on_event(AgentAudio(AudioFrame.silence(22050, 1764)), 12.0)  # disclosure still playing
    assert iv.tick(18.0) == [], "only 6 s since the agent stopped"
    assert [a.text for a in iv.tick(19.0) if isinstance(a, Speak)] == [CONSENT_REASK]
    assert iv.tick(33.0) == [], "the wait runs again from the repeat"
    actions = iv.tick(34.0)
    assert [a.text for a in actions if isinstance(a, Speak)] == [CONSENT_UNANSWERED]
    assert [type(a) for a in actions if isinstance(a, EndCall)] == [EndCall]
    assert iv.record.consent is False
    assert iv.record.ended == "no answer to the consent question"


def test_the_consent_question_is_repeated_once_not_twice():
    from zeg.interview import Speak
    from zeg.prompts import CONSENT_REASK

    iv = Interview()
    iv.start()
    said = [a.text for t in range(1, 34) for a in iv.tick(float(t)) if isinstance(a, Speak)]
    assert said.count(CONSENT_REASK) == 1


def test_an_answer_to_the_repeated_consent_question_is_taken():
    from zeg.backends.base import UserTranscript

    iv = Interview()
    iv.start()
    for t in range(1, 20):
        iv.tick(float(t))
    iv.on_event(UserTranscript("oh sorry, yes that is fine", final=True), 22.0)
    assert iv.record.consent is True
    assert iv.record.ended is None


def test_a_hesitation_restarts_the_wait_for_a_consent_answer():
    from zeg.backends.base import UserTranscript
    from zeg.interview import EndCall

    iv = Interview()
    iv.start()
    iv.on_event(UserTranscript("um", final=True), 10.0)
    assert not [a for a in iv.tick(24.0) if isinstance(a, EndCall)]
    assert iv.record.consent is None


def test_a_silent_candidate_is_not_kept_on_a_recorded_call_without_consent():
    """This call ran the full 900 seconds with consent never given."""
    from zeg.prompts import CONSENT_UNANSWERED

    r = InterviewRunner(MockBackend()).run([CallerTurn("", speak_s=0.0, pause_after_s=1000.0)])
    assert r.consent is False
    assert r.ended == "no answer to the consent question"
    # Was 60. The consent question is now repeated once into silence, which is worth
    # about fifteen seconds of a call that would otherwise have ended on the first wait.
    assert r.duration_s < 75
    assert any(t.speaker == "agent" and t.text == CONSENT_UNANSWERED for t in r.transcript)
    assert r.agent_audio_frames > 0


def test_a_shorter_call_still_tells_the_candidate_it_is_closing():
    """The wrap-up was a fixed 810 seconds. On a ten-minute call it was due after the call
    had ended, so the call simply stopped without the candidate being told."""
    from zeg.prompts import WRAP_UP

    caller = [CONSENT, CallerTurn("we rewrote the payment reconciler after an outage",
                                  speak_s=4.0, pause_after_s=700.0)]
    r = run(caller, call=CallConfig(max_duration_s=600))
    wrap = [t for t in r.transcript if t.speaker == "agent" and t.text == WRAP_UP]
    assert len(wrap) == 1, "never told the interview was closing"
    assert wrap[0].at_s < 600
    assert r.ended == "time limit reached"


class RecordsCloses(OneAtATime):
    """Notes, for every session closed, whether the caller was mid-turn at the time."""

    def __init__(self):
        super().__init__()
        self.closed_mid_turn = []

    def start_session(self, system_prompt, greeting=None):
        session = super().start_session(system_prompt, greeting=greeting)
        close = session.close

        def recording_close():
            if not session._closed:
                self.closed_mid_turn.append(session.caller_speaking)
            close()

        session.close = recording_close
        return session


def test_a_rollover_waits_for_the_caller_to_finish_their_turn():
    """The rollover ran the moment it was asked for. A candidate who had carried on
    talking had the session closed under them, and what it had heard was lost."""
    backend = RecordsCloses()
    quick = [CONSENT] + [CallerTurn("we rewrote the payment reconciler after an outage",
                                    speak_s=8.0, pause_after_s=0.1)] * 8
    iv = Interview(rollover=RolloverPolicy(context_horizon_s=20, min_session_s=10))
    r = InterviewRunner(backend, interview=iv).run(quick)

    assert r.rollovers >= 1, "the call never rolled, so this proves nothing"
    assert True not in backend.closed_mid_turn, backend.closed_mid_turn
    assert len(backend.sessions) == r.rollovers + 1
    assert len(caller_turns(r)) == len(quick)


def test_a_session_reports_whether_the_caller_is_mid_turn():
    session = MockBackend().start_session("sys")
    assert not session.caller_speaking
    loud = tone(16000, 320, amplitude=0.3)
    session.push_audio(loud)
    assert session.caller_speaking
    for _ in range(15):
        session.push_audio(AudioFrame.silence(16000, 320))
    assert not session.caller_speaking


class RefusesTheSecondSession(MockBackend):
    """A backend that will not open another session, as the runtime may refuse."""

    def __init__(self):
        super().__init__()
        self.starts = 0

    def start_session(self, system_prompt, greeting=None):
        self.starts += 1
        if self.starts > 1:
            raise RuntimeError("the speech runtime refused the connection")
        return super().start_session(system_prompt, greeting=greeting)


def test_a_rollover_that_cannot_open_a_session_still_returns_the_interview():
    """The old session is closed before the new one opens, so a refused session ends
    the call. It used to escape the runner instead: no transcript, no report, over a
    failure that is reachable every hundred seconds of a long call."""
    backend = RefusesTheSecondSession()
    caller = [CONSENT] + [CallerTurn("we rewrote the payment reconciler after an outage",
                                     speak_s=8.0, pause_after_s=2.0)] * 8
    iv = Interview(rollover=RolloverPolicy(context_horizon_s=20, min_session_s=10))

    r = InterviewRunner(backend, interview=iv).run(caller)

    assert backend.starts > 1, "the call never tried to roll, so this proves nothing"
    assert r.failed
    assert r.ended == "backend failed: could not open a new session"
    assert any("refused the connection" in e for e in r.errors)
    assert [t for t in r.transcript if t.speaker == "caller"], "what was said comes back"
    assert r.rollovers == 0, "a rollover that did not happen is not counted"


def test_a_long_probe_ladder_does_not_keep_a_session_past_the_models_window():
    """A candidate giving long, specific answers kept the ladder going, and the ladder
    blocked every rollover. Measured: sessions lived 246 and 227 seconds against a model
    that holds about 120."""
    from zeg.interview import Rollover

    answers = [
        "we rewrote the payment reconciler after an outage because batches were settled twice",
        "I wrote the advisory lock fix myself and the reproduction harness around it",
        "it caused eleven double settlements in six weeks, about forty thousand dollars",
        "we gave up about fifteen percent write throughput because the lock serialises writers",
        "a nightly batch job deadlocked against the lock because it took rows in another order",
    ]
    caller = [CONSENT] + [CallerTurn(a, speak_s=40.0, pause_after_s=2.0) for a in answers] * 2
    iv = Interview()
    started, ages = [0.0], []
    on_event = iv.on_event

    def watching(event, t_s):
        actions = on_event(event, t_s)
        if any(isinstance(a, Rollover) for a in actions):
            ages.append(t_s - started[-1])
            started.append(t_s)
        return actions

    iv.on_event = watching
    r = InterviewRunner(MockBackend(), interview=iv).run(caller)
    ages.append(r.duration_s - started[-1])

    assert r.rollovers >= 1
    assert max(ages) < 160, "a session lived %.0f s: %s" % (max(ages), [round(a) for a in ages])


def test_a_session_reports_whether_the_agent_is_still_speaking():
    session = MockBackend().start_session("sys", greeting="hello there")
    assert session.agent_speaking
    for _ in range(400):
        session.push_audio(AudioFrame.silence(16000, 320))
    assert not session.agent_speaking


def test_a_rebuilt_seed_carries_the_question_just_asked():
    """The rollover happens later than it is asked for, and by then the agent has
    usually asked the question the fresh session most needs to know about."""
    from zeg.backends.base import AgentText, UserTranscript

    iv = consented_interview()
    iv.on_event(UserTranscript("we rewrote the payment reconciler", final=True), 100)
    before = iv.seed(101).context()
    iv.on_event(AgentText("What did you personally do there?", final=True), 102)
    after = iv.seed(103).context()
    assert "What did you personally do there?" not in before
    assert "What did you personally do there?" in after


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

    def tick(self, t_s):
        return []


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


def test_audio_is_still_counted_once_the_call_has_already_ended():
    """The end of a call waits for its final line by counting agent audio. Reading
    stopped after the first event of every batch once the call had ended, so audio
    behind a text event was never counted, and the wait could give up mid-sentence."""
    from zeg.audio import AudioFrame
    from zeg.backends import AgentAudio, AgentText
    from zeg.conversation import DrivenResult, _VirtualClock

    frame = AudioFrame.silence(22050, 441)
    runner = InterviewRunner(MockBackend(), interview=_Stub(None))
    runner._session = _OldSession([AgentText("That is completely fine.", final=True),
                                   AgentAudio(frame), AgentAudio(frame)])
    runner._saying = None
    result = DrivenResult(ended="consent declined")
    runner._consume(_VirtualClock(runner.audio.frame_ms), result, lambda actions: None)
    assert result.agent_audio_frames == 2


# --- only the interview itself is scored, end to end --------------------------------


def test_a_driven_call_does_not_score_the_consent_answer():
    """A consent answer with a reason in it was quoted as technical evidence."""
    from zeg.scoring import score_call

    r = run([CallerTurn("yes that is fine, because I want the recruiter to hear it", speak_s=2.0)])
    assert r.consent is True
    a = score_call(r.transcript, window=r.interview_window)
    quotes = [e.quote for d in a.dimensions for e in d.evidence]
    assert not any("recruiter to hear it" in q for q in quotes)


def test_a_declined_call_has_an_empty_interview_window():
    from zeg.scoring import to_qa_units

    r = run([CallerTurn("no thank you", speak_s=1.5)])
    assert to_qa_units(r.transcript, window=r.interview_window) == []


def test_the_demo_report_scores_only_the_interview():
    """The command line scored the whole transcript, consent exchange included.

    This used to check the command line's source for a literal argument, which passed or
    failed on how the code was written rather than on what it did.
    """
    from zeg.cli import report_for
    from zeg.conversation import DrivenResult, TranscriptEntry as T

    result = DrivenResult()
    result.transcript = [
        T(0, "agent", "Is it okay if this call is recorded?"),
        T(5, "caller", "Yes, I wrote the advisory lock fix myself because two workers read one batch."),
        T(10, "agent", "Tell me about a recent project."),
        T(20, "caller", "We moved the ledger to its own database."),
    ]
    result.consent = True
    result.interview_started_s = 5
    quotes = [e.quote for d in report_for(result).dimensions for e in d.evidence]
    assert not any("advisory lock" in q for q in quotes), "the consent answer was scored"
