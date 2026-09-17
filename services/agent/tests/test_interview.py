import pytest

from zeg.backends.base import AgentInterrupted, AgentText, UserTranscript
from zeg.config import CallConfig
from zeg.engine import InterviewEngine
from zeg.interview import Brief, EndCall, Interview, Probe, Speak
from zeg.scoring import score_call


@pytest.fixture
def iv():
    return Interview()


def consented(iv, t=5.0):
    iv.start()
    iv.on_event(UserTranscript("yes that is fine", final=True), t)
    return iv


def spoken(actions):
    return [a.text for a in actions if isinstance(a, Speak)]


def briefs(actions):
    return [a.text for a in actions if isinstance(a, Brief)]


def probes(actions):
    return [a.instruction for a in actions if isinstance(a, Probe)]


# --- the opening -------------------------------------------------------------


def test_the_call_opens_with_disclosure_and_a_consent_request(iv):
    said = spoken(iv.start())[0]
    assert "AI interviewer" in said
    assert "recorded" in said


def test_consent_granted_lets_the_interview_proceed(iv):
    iv.start()
    iv.on_event(UserTranscript("yes that's fine", final=True), 5)
    assert iv.record.consent is True
    assert iv.record.ended is None


def test_consent_refused_ends_the_call(iv):
    iv.start()
    actions = iv.on_event(UserTranscript("no, I'd rather you didn't", final=True), 5)
    assert iv.record.consent is False
    assert any(isinstance(a, EndCall) for a in actions)
    assert "recruiting team" in spoken(actions)[0]


def test_an_ambiguous_answer_is_not_consent(iv):
    """Silence and hedging are not agreement. A bare hesitation is now waited through
    rather than read as a refusal, so it must simply never grant consent; a real hedge
    is still judged, and judged as not consent."""
    iv.start()
    iv.on_event(UserTranscript("hmm", final=True), 5)
    assert iv.record.consent is not True
    iv.on_event(UserTranscript("I guess so", final=True), 8)
    assert iv.record.consent is False


def test_nothing_happens_after_the_call_ends(iv):
    iv.start()
    iv.on_event(UserTranscript("no", final=True), 5)
    assert iv.on_event(UserTranscript("wait, actually yes", final=True), 10) == []


# --- the clock outranks the conversation -------------------------------------


def test_wrap_up_fires_once_the_clock_says_so(iv):
    consented(iv)
    actions = iv.on_event(UserTranscript("we rewrote the reconciler", final=True), 815)
    assert any("time I have" in s for s in spoken(actions))


def test_wrap_up_does_not_repeat(iv):
    consented(iv)
    iv.on_event(UserTranscript("a claim about latency", final=True), 815)
    again = iv.on_event(UserTranscript("another claim entirely", final=True), 830)
    assert not [s for s in spoken(again) if "time I have" in s]


def test_the_hard_limit_ends_the_call_whatever_is_happening(iv):
    consented(iv)
    actions = iv.on_event(UserTranscript("still talking", final=True), 901)
    assert any(isinstance(a, EndCall) for a in actions)
    assert iv.record.ended == "time limit reached"


def test_a_shorter_call_config_moves_both_limits():
    short = Interview(call=CallConfig(max_duration_s=120, wrap_up_at_s=90))
    consented(short)
    assert any(isinstance(a, EndCall) for a in
               short.on_event(UserTranscript("x", final=True), 121))


# --- memory ------------------------------------------------------------------


def test_the_model_is_re_grounded_when_the_phase_moves(iv):
    consented(iv)
    actions = iv.on_event(UserTranscript("we cut latency to 30ms", final=True), 200)
    assert briefs(actions), "a phase change should re-ground the model"


def test_the_briefing_is_resent_when_it_goes_stale(iv):
    """The model holds about two minutes; a briefing older than that is worthless."""
    consented(iv)
    iv.on_event(UserTranscript("we cut latency to 30ms", final=True), 200)
    quiet = iv.on_event(UserTranscript("and it held up", final=True), 210)
    assert not briefs(quiet)
    later = iv.on_event(UserTranscript("then we sharded it", final=True), 280)
    assert briefs(later)


def test_the_briefing_carries_the_claim_the_model_will_forget(iv):
    consented(iv)
    actions = iv.on_event(UserTranscript("we cut reconciler latency to 30ms", final=True), 200)
    assert "reconciler" in briefs(actions)[0]


def test_probes_are_suggested_after_a_specific_answer(iv):
    consented(iv)
    actions = iv.on_event(UserTranscript("we rewrote the payment reconciler", final=True), 200)
    assert any("Ask for" in p for p in probes(actions))


def test_a_probe_is_not_a_briefing(iv):
    """The caller must be able to tell context from an instruction."""
    consented(iv)
    actions = iv.on_event(UserTranscript("we rewrote the payment reconciler", final=True), 200)
    assert probes(actions) and all("Ask for" not in b for b in briefs(actions))


# --- the block list ----------------------------------------------------------


def test_a_prohibited_question_is_dropped_not_spoken(iv):
    consented(iv)
    actions = iv._say("Are you married?", 100)
    assert spoken(actions) == []
    assert any("Blocked a prohibited question" in f for f in iv.record.flags)


def test_a_blocked_question_never_reaches_the_transcript(iv):
    consented(iv)
    iv._say("How old are you?", 100)
    assert not [t for t in iv.record.transcript if "old are you" in t.text]


def test_an_ordinary_question_passes_through(iv):
    consented(iv)
    assert spoken(iv._say("What broke afterwards?", 100)) == ["What broke afterwards?"]


# --- recording ----------------------------------------------------------------


def test_both_sides_land_in_the_transcript(iv):
    consented(iv)
    iv.on_event(AgentText("Tell me about a bug.", final=True), 100)
    iv.on_event(UserTranscript("a race in the reconciler", final=True), 110)
    speakers = [t.speaker for t in iv.record.transcript]
    assert "agent" in speakers and "caller" in speakers


def test_partial_transcripts_are_not_recorded(iv):
    consented(iv)
    before = len(iv.record.transcript)
    iv.on_event(UserTranscript("a race in the", final=False), 110)
    assert len(iv.record.transcript) == before


def test_an_interruption_does_not_derail_the_interview(iv):
    consented(iv)
    assert iv.on_event(AgentInterrupted(), 100) == []
    assert iv.record.ended is None


def test_the_record_feeds_the_scoring_pass_directly(iv):
    consented(iv)
    iv.on_event(AgentText("What did you do?", final=True), 100)
    iv.on_event(UserTranscript("i wrote the advisory-lock fix because of a double read", final=True), 110)
    a = score_call(iv.transcript_for_scoring())
    assert a.dimensions, "the interview record should score without translation"


def test_a_declined_call_scores_as_insufficient_signal(iv):
    iv.start()
    iv.on_event(UserTranscript("no thanks", final=True), 5)
    assert score_call(iv.transcript_for_scoring()).band == "insufficient signal"


def test_an_engine_can_be_supplied(iv):
    eng = InterviewEngine()
    other = Interview(engine=eng)
    other.start()
    assert other.engine is eng


# --- after the wrap-up ---------------------------------------------------------


def test_no_probe_is_issued_once_the_interview_has_wrapped_up(iv):
    """Only the answer that triggered the wrap-up stopped short of probing. Every later
    answer started or continued a ladder, so the agent said it was out of time and then
    kept asking, even answering the candidate's own question with a probe."""
    consented(iv)
    iv.on_event(UserTranscript("we rewrote the payment reconciler after an outage", final=True), 790)
    iv.on_event(UserTranscript("I wrote the advisory lock fix myself", final=True), 800)
    wrap = iv.on_event(UserTranscript("we cut p99 latency from 400ms to 30ms", final=True), 815)
    assert any("time I have" in s for s in spoken(wrap))

    after = []
    for t, text in [(825, "we gave up strict ordering across shards"),
                    (835, "a downstream report started double counting"),
                    (845, "we fixed the report join afterwards"),
                    (855, "do you have any questions for me?")]:
        after.extend(iv.on_event(UserTranscript(text, final=True), t))
    assert not probes(after), "still probing after saying it was out of time: %s" % probes(after)


def test_no_rollover_happens_once_the_interview_has_wrapped_up():
    """A policy eager enough to roll on every turn must still not pay for a fresh session
    and an audible pause in the closing minute and a half."""
    from zeg.interview import Rollover
    from zeg.memory import RolloverPolicy

    iv = Interview(rollover=RolloverPolicy(context_horizon_s=20, min_session_s=10))
    consented(iv)
    after = []
    for t in (815, 825, 835, 845):
        after.extend(iv.on_event(UserTranscript("we basically did various things", final=True), t))
    assert not [a for a in after if isinstance(a, Rollover)]


# --- talking over the disclosure ------------------------------------------------


def test_consent_is_not_taken_from_someone_who_talked_over_the_disclosure(iv):
    """An interruption before consent was ignored, so whatever the candidate said over
    the disclosure counted as their answer. Saying yeah over "this call is recorded"
    put them on record as consenting to a recording they may never have heard."""
    from zeg.backends.base import AgentInterrupted

    iv.start()
    iv.on_event(AgentInterrupted(), 2.0)
    actions = iv.on_event(UserTranscript("yeah go ahead", final=True), 3.0)

    assert iv.record.consent is None, "consent taken over an interrupted disclosure"
    assert any("AI interviewer" in s for s in spoken(actions)), "the disclosure was not repeated"
    assert any("talked over the recording disclosure" in f for f in iv.record.flags)

    iv.on_event(UserTranscript("yes that is fine", final=True), 20.0)
    assert iv.record.consent is True


def test_agreeing_over_the_answer_to_a_consent_question_is_consent(iv):
    """The disclosure was heard in full and the candidate asked about it. Saying "that's
    fine" over the answer discarded the consent, replayed the whole greeting, and flagged
    them for talking over the disclosure."""
    from zeg.backends.base import AgentInterrupted

    iv.start()
    iv.on_event(UserTranscript("what happens to the recording?", final=True), 16.0)
    iv.on_event(AgentInterrupted("barge_in"), 19.0)
    actions = iv.on_event(UserTranscript("oh okay, that's fine", final=True), 21.0)

    assert iv.record.consent is True
    assert not any("AI interviewer" in s for s in spoken(actions))
    assert not [f for f in iv.record.flags if "disclosure" in f]


def test_a_repeated_disclosure_can_be_talked_over_again(iv):
    from zeg.backends.base import AgentInterrupted

    iv.start()
    actions = iv.on_event(UserTranscript("sorry, could you repeat that?", final=True), 14.0)
    assert any("AI interviewer" in s for s in spoken(actions)), "the disclosure was not repeated"
    iv.on_event(AgentInterrupted("barge_in"), 16.0)
    iv.on_event(UserTranscript("yeah go ahead", final=True), 17.0)
    assert iv.record.consent is None
    assert any("talked over the recording disclosure" in f for f in iv.record.flags)


def test_an_interruption_after_consent_does_not_ask_again(iv):
    from zeg.backends.base import AgentInterrupted

    consented(iv)
    iv.on_event(AgentInterrupted(), 30.0)
    actions = iv.on_event(UserTranscript("we rewrote the payment reconciler", final=True), 35.0)
    assert iv.record.consent is True
    assert not any("AI interviewer" in s for s in spoken(actions))


# --- the interview's own boundaries, for scoring ----------------------------------


def test_the_record_marks_when_the_interview_proper_began(iv):
    consented(iv, t=5.0)
    assert iv.record.interview_started_s == 5.0


def test_a_declined_call_has_no_interview_to_score(iv):
    iv.start()
    iv.on_event(UserTranscript("no thanks", final=True), 5.0)
    assert iv.record.interview_started_s is None


def test_the_record_marks_when_the_interview_wrapped_up(iv):
    consented(iv)
    iv.on_event(UserTranscript("we rewrote the payment reconciler", final=True), 815)
    assert iv.record.wrapped_up_s == 815


# --- hesitating before answering the consent question ----------------------------


@pytest.mark.parametrize("sound", ["um", "uh...", "hmm", "well", "so um", "Um.", ""])
def test_a_hesitation_does_not_end_the_call_before_the_candidate_answers(sound):
    """The client ends a turn after 640 ms of silence, so "um" and a pause arrive as a
    complete answer. Read as a refusal, it ended the interview before they answered."""
    iv = Interview()
    iv.start()
    actions = iv.on_event(UserTranscript(sound, final=True), 5.0)
    assert not any(isinstance(a, EndCall) for a in actions)
    assert iv.record.consent is None


@pytest.mark.parametrize("words", [
    "hmm, let me think", "good question, give me a second", "uh, hold on",
])
def test_asking_for_time_does_not_end_the_call_before_the_candidate_answers(words):
    """Read as not agreeing, the call ended as declined on someone still deciding, and
    they were told the team would arrange a call with a person."""
    iv = Interview()
    iv.start()
    actions = iv.on_event(UserTranscript(words, final=True), 14.0)
    assert not any(isinstance(a, EndCall) for a in actions)
    assert iv.record.consent is None
    iv.on_event(UserTranscript("okay, yes that is fine", final=True), 20.0)
    assert iv.record.consent is True


def test_asking_for_time_with_an_answer_in_it_is_an_answer():
    from zeg.hesitation import is_hesitation

    assert not is_hesitation("good question, we used kafka for the queue")
    assert not is_hesitation("let me think about the rollout order")


def test_the_answer_after_a_hesitation_is_the_one_that_counts(iv):
    iv.start()
    iv.on_event(UserTranscript("um", final=True), 5.0)
    iv.on_event(UserTranscript("yes that is fine", final=True), 8.0)
    assert iv.record.consent is True


def test_hesitating_without_ever_answering_does_not_hold_the_call_open(iv):
    """Checks the outcome, not which reply produced it: the old interview ended the call
    on the first hesitation, the fixed one on the third, and both must end it.

    The reason changed from "consent declined" to "no answer": hesitating is not
    refusing, and the record should not say the candidate declined.
    """
    iv.start()
    for t in (5.0, 8.0, 11.0):
        iv.on_event(UserTranscript("um", final=True), t)
    assert iv.record.consent is False
    assert iv.record.ended == "no answer to the consent question"


@pytest.mark.parametrize("words", ["um", "hmm, let me think", "uh, hold on"])
def test_running_out_of_patience_is_not_recorded_as_a_refusal(words):
    """Three "let me think"s put a refusal on the record and told the candidate that was
    completely fine. They never refused anything."""
    from zeg.interview import Speak
    from zeg.prompts import CONSENT_DECLINED, CONSENT_UNANSWERED

    iv = Interview()
    iv.start()
    spoken = []
    for t in (20.0, 40.0, 60.0):
        spoken += [a.text for a in iv.on_event(UserTranscript(words, final=True), t)
                   if isinstance(a, Speak)]
    assert iv.record.ended == "no answer to the consent question"
    assert CONSENT_UNANSWERED in spoken
    assert CONSENT_DECLINED not in spoken


def test_a_refusal_after_hesitating_is_still_a_refusal():
    from zeg.prompts import CONSENT_DECLINED

    iv = Interview()
    iv.start()
    iv.on_event(UserTranscript("um", final=True), 20.0)
    actions = iv.on_event(UserTranscript("no thanks", final=True), 40.0)
    assert iv.record.ended == "consent declined"
    assert any(getattr(a, "text", "") == CONSENT_DECLINED for a in actions)


def test_a_reply_that_starts_with_a_hesitation_is_still_an_answer(iv):
    iv.start()
    iv.on_event(UserTranscript("um, no thanks", final=True), 5.0)
    assert iv.record.consent is False
    other = Interview()
    other.start()
    other.on_event(UserTranscript("uh, yes", final=True), 5.0)
    assert other.record.consent is True


def test_an_acknowledgement_that_may_mean_yes_is_judged_not_waited_on(iv):
    """mm-hmm often means yes, so the hesitation rule must not swallow it."""
    iv.start()
    iv.on_event(UserTranscript("mm-hmm", final=True), 5.0)
    assert iv.record.consent is not None


# --- hesitating in the middle of an answer ---------------------------------------


def _claim_with_first_probe(iv):
    consented(iv)
    iv.on_event(UserTranscript("we rewrote the payment reconciler after an outage", final=True), 30)


def test_a_hesitation_mid_answer_does_not_use_up_a_probe(iv):
    """The ladder took "um" as the answer to its outstanding question and asked the next,
    so every later answer was credited to the wrong question."""
    from zeg.engine import PROBE_LADDER

    _claim_with_first_probe(iv)
    assert iv.engine.state.claims[-1].probed_to == 1
    actions = iv.on_event(UserTranscript("um", final=True), 40)
    assert probes(actions) == []
    assert iv.engine.state.claims[-1].probed_to == 1
    actions = iv.on_event(UserTranscript("I wrote the advisory lock fix myself", final=True), 50)
    assert probes(actions) == ["Ask for %s." % PROBE_LADDER[1]]


def test_a_hesitation_does_not_replace_the_session():
    from zeg.interview import Rollover
    from zeg.memory import RolloverPolicy

    iv = Interview(rollover=RolloverPolicy(context_horizon_s=20, min_session_s=10))
    consented(iv)
    actions = iv.on_event(UserTranscript("um", final=True), 40)
    assert not [a for a in actions if isinstance(a, Rollover)]


def test_a_hesitation_does_not_revive_a_stalled_ladder(iv):
    """Two vague answers stall the ladder. Read as an answer, "um" reset that count and
    the questions started again."""
    _claim_with_first_probe(iv)
    iv.on_event(UserTranscript("we basically did various things", final=True), 40)
    iv.on_event(UserTranscript("pretty much just stuff", final=True), 50)
    assert iv.engine.ladder_stalled
    actions = iv.on_event(UserTranscript("um", final=True), 60)
    assert iv.engine.ladder_stalled
    assert probes(actions) == []


def test_a_hesitation_after_the_wrap_up_time_still_wraps_up(iv):
    """The clock outranks the conversation, hesitation or not."""
    consented(iv)
    actions = iv.on_event(UserTranscript("um", final=True), 815)
    assert any("time I have" in s for s in spoken(actions))


# --- the report, for a driver holding the Interview directly ----------------------------


def a_call_with_a_flag_and_a_reasoned_consent(iv):
    iv.start()
    iv.on_event(AgentInterrupted("barge_in"), 3.0)          # talked over the disclosure
    iv.on_event(UserTranscript("yes", final=True), 5.0)      # the disclosure is repeated
    iv.on_event(UserTranscript("yes that is fine because I want the feedback", final=True), 20.0)
    iv.on_event(AgentText("What did you personally do?", final=True), 30.0)
    iv.on_event(UserTranscript("I wrote the advisory lock fix myself", final=True), 40.0)
    return iv


def test_the_interviews_report_scores_only_the_interview_and_keeps_its_flags(iv):
    """A driver holding the Interview had only transcript_for_scoring(). Scoring that
    directly, the obvious thing to do, dropped every compliance flag and scored the
    consent answer as if it answered an interview question."""
    a_call_with_a_flag_and_a_reasoned_consent(iv)

    direct = score_call(iv.transcript_for_scoring())
    assert not any("talked over" in f for f in direct.flags), "what the old path lost"

    report = iv.report()
    assert any("talked over the recording disclosure" in f for f in report.flags)
    assert any("interview is incomplete" in f for f in report.flags)
    quotes = [e.quote for d in report.dimensions for e in d.evidence]
    assert not any("feedback" in q for q in quotes), "the consent answer is not evidence"


def test_the_runner_and_the_interview_produce_the_same_report():
    """One assembly, so the demo and a driver using the Interview cannot disagree."""
    from zeg.backends import MockBackend
    from zeg.cli import report_for
    from zeg.conversation import CallerTurn, InterviewRunner

    iv = Interview()
    caller = [CallerTurn("yes that is fine", speak_s=1.5),
              CallerTurn("I wrote the advisory lock fix myself because two workers read "
                         "one batch", speak_s=5.0)]
    result = InterviewRunner(MockBackend(), interview=iv).run(caller)
    ours, theirs = report_for(result), iv.report(errors=result.errors)
    assert (ours.overall, ours.band, ours.flags) == (theirs.overall, theirs.band, theirs.flags)


# --- a candidate who goes quiet after a question -----------------------------------------


def asked_and_waiting(iv, at=100.0):
    """Consent given, an answer, then the agent's question heard ending at `at`."""
    from zeg.audio import AudioFrame
    from zeg.backends.base import AgentAudio

    consented(iv)
    iv.on_event(UserTranscript("we rewrote the payment reconciler after an outage", final=True), at - 30)
    iv.on_event(AgentAudio(AudioFrame.silence(22050, 1764)), at)
    return iv


def test_a_silent_candidate_is_nudged_then_moved_on(iv):
    """The silence settings were used nowhere, and the model only speaks after a caller
    turn, so a candidate who went quiet got silence back until the wrap-up."""
    from zeg.prompts import SILENCE_MOVE_ON, SILENCE_NUDGE

    asked_and_waiting(iv)
    assert iv.tick(103.0) == []
    assert spoken(iv.tick(104.0)) == [SILENCE_NUDGE]
    assert iv.tick(110.0) == []
    actions = iv.tick(115.0)
    assert spoken(actions) == [SILENCE_MOVE_ON]
    assert any(isinstance(a, Brief) for a in actions)
    assert iv.tick(200.0) == [], "each is said once per silence"


def test_moving_on_abandons_the_question_that_went_unanswered(iv):
    asked_and_waiting(iv)
    assert iv.engine.probe_in_progress
    iv.tick(104.0)
    iv.tick(115.0)
    assert not iv.engine.probe_in_progress


def test_a_candidate_who_answers_after_the_nudge_is_not_moved_on(iv):
    asked_and_waiting(iv)
    iv.tick(104.0)
    iv.on_event(UserTranscript("I wrote the advisory lock fix myself", final=True), 107.0)
    assert iv.tick(130.0) == [], "the model owes the reply now, not us"


def test_no_nudge_while_the_model_owes_the_reply(iv):
    """After the candidate spoke, the silence is the model's to fill."""
    consented(iv)
    iv.on_event(UserTranscript("we rewrote the payment reconciler", final=True), 100.0)
    assert iv.tick(120.0) == []


def test_no_nudge_after_the_wrap_up(iv):
    from zeg.audio import AudioFrame
    from zeg.backends.base import AgentAudio

    consented(iv)
    iv.tick(850.0)  # the wrap-up
    iv.on_event(AgentAudio(AudioFrame.silence(22050, 1764)), 852.0)
    assert iv.tick(870.0) == []


# --- who cut the disclosure off --------------------------------------------------------


@pytest.mark.parametrize("reason", ["no_progress", "trailing_silence", ""])
def test_a_disclosure_cut_off_by_the_system_is_not_blamed_on_the_candidate(iv, reason):
    """Every interruption was recorded as the candidate talking over the disclosure,
    including a runtime stopping a stalled response."""
    iv.start()
    iv.on_event(AgentInterrupted(reason), 4.0)
    actions = iv.on_event(UserTranscript("yes that is fine", final=True), 6.0)
    assert any("AI interviewer" in s for s in spoken(actions)), "it is still repeated"
    assert not any("candidate talked over" in f for f in iv.record.flags)
    assert any("cut off by the system" in f for f in iv.record.flags)


@pytest.mark.parametrize("reason", ["barge_in", "superseded"])
def test_a_candidate_talking_over_the_disclosure_is_still_recorded_as_such(iv, reason):
    iv.start()
    iv.on_event(AgentInterrupted(reason), 4.0)
    iv.on_event(UserTranscript("yes that is fine", final=True), 6.0)
    assert any("candidate talked over the recording disclosure" in f for f in iv.record.flags)


# --- a question instead of an answer, at the consent gate ----------------------------


def test_a_question_at_the_consent_gate_is_answered_not_refused(iv):
    """Every one of these ended the call and played the line written for a refusal at
    somebody who had not refused anything."""
    iv.start()
    actions = iv.on_event(UserTranscript("what happens to the recording?", final=True), 5)

    assert iv.record.ended is None
    assert iv.record.consent is None
    said = spoken(actions)
    assert said, "the candidate's question went unanswered"
    assert "human reviewer" in said[0]
    assert "is it okay with you if I record" in said[0]


def test_the_agent_says_it_is_an_ai_when_asked(iv):
    iv.start()
    said = spoken(iv.on_event(UserTranscript("are you a real person?", final=True), 5))
    assert said and said[0].startswith("Yes, I am an AI interviewer")
    assert iv.record.ended is None


def test_a_request_to_repeat_gets_the_disclosure_again(iv):
    from zeg.prompts import GREETING

    iv.start()
    said = spoken(iv.on_event(UserTranscript("sorry, could you repeat that?", final=True), 5))
    assert said == [GREETING]


def test_a_yes_after_a_question_is_consent(iv):
    iv.start()
    iv.on_event(UserTranscript("what happens to the recording?", final=True), 5)
    iv.on_event(UserTranscript("okay, that is fine", final=True), 14)
    assert iv.record.consent is True
    assert iv.record.ended is None


def test_a_refusal_after_a_question_is_still_a_refusal(iv):
    iv.start()
    iv.on_event(UserTranscript("what happens to the recording?", final=True), 5)
    iv.on_event(UserTranscript("I'd rather not, then", final=True), 14)
    assert iv.record.consent is False
    assert iv.record.ended == "consent declined"


def test_a_refusal_with_a_question_in_it_is_not_answered_back(iv):
    """Answering and asking again would be pressing somebody who has said no."""
    iv.start()
    iv.on_event(UserTranscript("no, what happens to the recording?", final=True), 5)
    assert iv.record.consent is False
    assert iv.record.ended == "consent declined"


def test_questions_do_not_go_on_forever(iv):
    """A candidate who only ever asks is not agreeing, and an agent that answers for
    ever is one they cannot get off the line."""
    iv.start()
    for t in (5, 14, 23):
        iv.on_event(UserTranscript("what happens to the recording?", final=True), t)
    assert iv.record.consent is False
    assert iv.record.ended == "consent declined"


# --- a question from the candidate, mid-interview -------------------------------------


@pytest.mark.parametrize("question", [
    "Sorry, what does this team actually work on day to day?",
    "How does the team split on-call between people",
    "Can you tell me more about the role first?",
])
def test_a_candidates_question_is_not_taken_as_a_claim(iv, question):
    """"What does this team work on?" became a claim, and the model was told to ask what
    the candidate personally did about their own question."""
    consented(iv)
    actions = iv.on_event(UserTranscript(question, final=True), 200)
    assert iv.engine.state.claims == []
    assert not [a for a in actions if isinstance(a, Probe)]


def test_an_answer_starting_with_what_is_still_a_claim(iv):
    consented(iv)
    actions = iv.on_event(
        UserTranscript("What I did was rewrite the reconciler after the outage", final=True), 200
    )
    assert len(iv.engine.state.claims) == 1
    assert [a for a in actions if isinstance(a, Probe)]


def test_an_answer_with_a_question_mark_on_it_is_still_an_answer(iv):
    consented(iv)
    iv.on_event(UserTranscript("we cut p99 from 400ms to 30ms, right?", final=True), 200)
    assert len(iv.engine.state.claims) == 1


# --- asking to stop, once the interview is under way ---------------------------------


def test_a_candidate_who_asks_for_a_person_gets_one(iv):
    """The disclosure offers this in the first sentence of the call. Asked for a person,
    the interview used to issue its next probe."""
    from zeg.prompts import HUMAN_REQUESTED

    consented(iv)
    actions = iv.on_event(UserTranscript("I'd rather speak to a person", final=True), 200)

    assert spoken(actions) == [HUMAN_REQUESTED]
    assert any(isinstance(a, EndCall) for a in actions)
    assert not [a for a in actions if isinstance(a, Probe)]
    assert iv.record.ended == "human requested"
    assert any("asked to speak to a person at 3:20" in f for f in iv.record.flags)


def test_the_agent_admits_what_it_is_mid_interview(iv):
    """Saying yes immediately is policy, and it was left to the system prompt."""
    from zeg.prompts import CONSENT_ANSWERS

    consented(iv)
    actions = iv.on_event(UserTranscript("wait, are you a real person?", final=True), 200)

    assert spoken(actions) == [CONSENT_ANSWERS["ai"]]
    assert not [a for a in actions if isinstance(a, Probe)]
    assert iv.record.ended is None


def test_a_question_about_the_agent_is_not_an_answer(iv):
    """It starts no claim and moves no ladder: the candidate was asking, not answering."""
    consented(iv)
    iv.on_event(UserTranscript("am I talking to a bot?", final=True), 200)
    assert iv.engine.state.claims == []


def test_an_answer_that_mentions_a_colleague_is_left_alone(iv):
    consented(iv)
    actions = iv.on_event(
        UserTranscript("I spoke to the on-call engineer and we rolled it back", final=True), 200
    )
    assert iv.record.ended is None
    assert spoken(actions) == []


def test_a_candidate_who_asks_to_stop_ends_the_call(iv):
    """Consent is not a gate that is passed once. This answer used to be treated as any
    other, and the interview carried on asking questions and recording them."""
    from zeg.prompts import CONSENT_WITHDRAWN

    consented(iv)
    actions = iv.on_event(
        UserTranscript("actually, can you stop the recording?", final=True), 372
    )
    assert spoken(actions) == [CONSENT_WITHDRAWN]
    assert any(isinstance(a, EndCall) for a in actions)
    assert iv.record.ended == "consent withdrawn"
    assert any("asked to stop at 6:12" in f for f in iv.record.flags)
    assert any("A human must decide" in f for f in iv.record.flags)


def test_an_ordinary_answer_about_stopping_something_does_not_end_the_call(iv):
    consented(iv)
    iv.on_event(
        UserTranscript("we stopped the retries after the third attempt", final=True), 100
    )
    assert iv.record.ended is None


def test_nothing_is_asked_after_a_candidate_asks_to_stop(iv):
    consented(iv)
    iv.on_event(UserTranscript("I would like to stop", final=True), 200)
    later = iv.on_event(UserTranscript("sorry, what was that?", final=True), 210)
    assert later == []


def test_asking_to_stop_before_consent_is_a_refusal(iv):
    """The consent gate runs first and already refuses this."""
    iv.start()
    iv.on_event(UserTranscript("please stop", final=True), 5)
    assert iv.record.consent is False
    assert iv.record.ended == "consent declined"


# --- the model asking something it must not ask -------------------------------------


def streamed(iv, deltas, t=100.0):
    """The agent's own reply arriving word by word, as the runtime sends it."""
    out = []
    for delta in deltas:
        out.extend(iv.on_event(AgentText(delta, final=False), t))
    return out


def test_a_prohibited_question_from_the_model_is_cut_off(iv):
    """The block list gates our own lines before they are spoken. The model speaks for
    itself, so this question reached the candidate's ear unflagged and unrecorded as a
    compliance event."""
    from zeg.prompts import PROHIBITED_REDIRECT

    consented(iv)
    actions = streamed(iv, ["So before we go on, ", "are you ", "married", "?"])

    assert spoken(actions) == [PROHIBITED_REDIRECT]
    assert any("prohibited question (family)" in f for f in iv.record.flags)


def test_the_model_is_told_the_subject_is_prohibited(iv):
    """The system prompt already forbids it and the model asked anyway, so without this
    the next turn is the same question again."""
    consented(iv)
    actions = streamed(iv, ["are you married", "?"])
    briefs = [a.text for a in actions if isinstance(a, Brief)]
    assert briefs, "the model was cut off and told nothing"
    assert "family" in briefs[0]
    assert "prohibited" in briefs[0]


def test_a_fresh_session_is_told_about_a_subject_already_refused(iv):
    """The briefing that came with the redirect lives in that session. A rollover opens
    a new one every hundred seconds, and it would start from the same system prompt the
    model has already ignored once."""
    consented(iv)
    streamed(iv, ["are you married?"])
    assert "Never ask about: family" in iv.seed(200).context()


def test_the_flag_claims_only_what_is_known(iv):
    """Saying a line cancels the model's reply, but how much the candidate heard
    depends on the backend and on how far ahead the audio was."""
    consented(iv)
    streamed(iv, ["are you married?"])
    flag = iv.record.flags[0]
    assert "asked a prohibited question (family)" in flag
    assert "may have heard part of it" in flag
    assert "was cut off" not in flag


def test_the_agent_is_only_cut_off_once_for_one_question(iv):
    consented(iv)
    streamed(iv, ["are you married", "?"])
    more = streamed(iv, [" I mean, are you married?"])
    assert spoken(more) == []
    assert len(iv.record.flags) == 1


def test_a_prohibited_question_that_only_arrives_whole_is_still_cut_off(iv):
    """A backend that reports the reply in one piece, rather than as it is spoken."""
    from zeg.prompts import PROHIBITED_REDIRECT

    consented(iv)
    actions = iv.on_event(AgentText("How old are you, by the way?", final=True), 100)
    assert spoken(actions) == [PROHIBITED_REDIRECT]
    assert any("prohibited question (age)" in f for f in iv.record.flags)


def test_an_ordinary_question_from_the_model_is_left_alone(iv):
    consented(iv)
    actions = streamed(iv, ["What did you ", "personally do ", "on that project?"])
    actions += iv.on_event(AgentText("What did you personally do on that project?", final=True), 101)
    assert spoken(actions) == []
    assert iv.record.flags == []


def test_the_next_reply_is_watched_again_after_a_redirect(iv):
    """The flag is per question, not per call."""
    consented(iv)
    streamed(iv, ["are you married?"])
    iv.on_event(AgentText("Sorry, let me stay on the technical side. Tell me more about "
                          "the part of that work you did yourself.", final=True), 101)
    actions = streamed(iv, ["and ", "where are you originally from", "?"], t=120)
    assert spoken(actions), "the second prohibited question was not cut off"
    assert len(iv.record.flags) == 2
