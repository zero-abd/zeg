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
    """Silence and hedging are not agreement."""
    iv.start()
    iv.on_event(UserTranscript("hmm", final=True), 5)
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
