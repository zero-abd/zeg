import pytest

from zeg.blocklist import ProhibitedQuestion
from zeg.config import CallConfig
from zeg.engine import DIMENSIONS, PROBE_LADDER, InterviewEngine


@pytest.fixture
def eng():
    return InterviewEngine()


def test_phases_follow_the_wall_clock(eng):
    assert eng.phase_at(0).name == "greeting"
    assert eng.phase_at(120).name == "warmup"
    assert eng.phase_at(300).name == "depth_one"
    assert eng.phase_at(600).name == "depth_two"
    assert eng.phase_at(700).name == "scenario"
    assert eng.phase_at(880).name == "close"


def test_phase_past_the_end_stays_at_close(eng):
    assert eng.phase_at(10_000).name == "close"


def test_advance_reports_only_real_transitions(eng):
    assert eng.advance(10) is None       # already in greeting
    assert eng.advance(120) == "warmup"
    assert eng.advance(130) is None      # same phase


def test_wrap_up_and_end_are_clock_driven(eng):
    assert not eng.should_wrap_up(800)
    assert eng.should_wrap_up(810)
    assert not eng.is_over(899)
    assert eng.is_over(900)


def test_a_specific_answer_becomes_a_claim(eng):
    eng.note_caller("we cut reconciler latency from 400ms to 30ms", 100)
    assert len(eng.state.claims) == 1


def test_a_vague_answer_does_not_become_a_claim(eng):
    eng.note_caller("we basically just did various things you know", 100)
    assert eng.state.claims == []
    assert eng.state.vague_streak == 1


def test_two_vague_answers_stop_the_probe_ladder(eng):
    eng.note_caller("we rewrote the payment reconciler after an outage", 100)
    assert eng.next_probe() is not None
    eng.note_caller("basically stuff like that", 110)
    eng.note_caller("you know, various things", 120)
    assert eng.next_probe() is None


def test_the_probe_ladder_descends_then_stops(eng):
    eng.note_caller("we rewrote the payment reconciler after an outage", 100)
    rungs = [eng.next_probe() for _ in range(len(PROBE_LADDER))]
    assert rungs == list(PROBE_LADDER)
    assert eng.next_probe() is None


def test_no_claim_means_no_probe(eng):
    assert eng.next_probe() is None


def test_uncovered_starts_complete_and_shrinks(eng):
    assert eng.uncovered() == list(DIMENSIONS)
    eng.record_evidence("ownership", "I wrote the fix", 200)
    assert "ownership" not in eng.uncovered()


def test_unknown_dimension_is_rejected(eng):
    with pytest.raises(ValueError):
        eng.record_evidence("charisma", "quote", 10)


def test_speak_gates_prohibited_questions(eng):
    assert eng.speak("What broke afterwards?") == "What broke afterwards?"
    with pytest.raises(ProhibitedQuestion):
        eng.speak("Are you married?")


def test_briefing_carries_what_the_model_cannot_remember(eng):
    eng.note_caller("we cut reconciler latency from 400ms to 30ms", 100)
    eng.record_evidence("ownership", "I wrote the fix", 120)
    b = eng.briefing(300)

    assert "5:00" in b                  # where we are
    assert "depth_one" in b             # what phase
    assert "reconciler" in b            # what they claimed
    assert "technical_depth" in b       # what still has no evidence
    assert "ownership" not in b.split("Still no evidence for:")[-1]


def test_briefing_says_to_close_when_time_is_nearly_up(eng):
    assert "Close the interview" in eng.briefing(870)


def test_briefing_flags_a_stalled_topic(eng):
    eng.note_caller("basically stuff", 100)
    eng.note_caller("you know, various things", 110)
    assert "Change topic" in eng.briefing(200)


def test_briefing_stays_short(eng):
    """It re-grounds the model. It is not a transcript replay."""
    for i in range(30):
        eng.note_caller("we shipped a thing that cut latency by %d percent" % i, i * 10)
    assert len(eng.briefing(400).splitlines()) <= 10


def test_a_shorter_call_moves_the_wrap_up(eng):
    short = InterviewEngine(call=CallConfig(max_duration_s=300, wrap_up_at_s=240))
    assert short.should_wrap_up(250)
    assert short.is_over(300)
