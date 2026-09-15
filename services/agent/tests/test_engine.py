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
    assert "tradeoffs" in b.split("Still no evidence for:")[-1]  # what still has none
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


# --- what the call has already covered ------------------------------------------------


def still_missing(eng, t_s=300):
    b = eng.briefing(t_s)
    return b.split("Still no evidence for:")[-1] if "Still no evidence for:" in b else ""


def test_an_answer_that_shows_ownership_takes_it_off_the_missing_list(eng):
    """Nothing recorded evidence during a call, so the briefing asked for ownership
    straight after the candidate said they wrote the fix themselves."""
    eng.note_caller("I wrote the advisory lock fix myself", 100)
    assert "ownership" not in still_missing(eng)
    assert "tradeoffs" in still_missing(eng)


def test_a_probe_answer_counts_as_evidence_too(eng):
    eng.note_caller("we rewrote the payment reconciler after an outage", 100)
    probe_and_answer(eng, ["I wrote the advisory lock fix myself",
                           "it caused eleven double settlements in six weeks",
                           "we gave up some write throughput to the lock"])
    missing = still_missing(eng)
    for dimension in ("ownership", "technical_depth", "tradeoffs"):
        assert dimension not in missing
    assert "debugging" in missing


def test_a_vague_answer_covers_nothing(eng):
    eng.note_caller("one of the things we did was basically improve stuff", 100)
    assert eng.uncovered() == list(DIMENSIONS)


def test_live_coverage_matches_what_the_heuristic_judge_scores(eng):
    """One set of markers, so the call cannot call a dimension covered that scoring
    then reports as having nothing."""
    from zeg.scoring import signals

    answer = "we found it because two workers picked up the same batch id"
    eng.note_caller(answer, 100)
    assert set(DIMENSIONS) - set(eng.uncovered()) == set(signals(answer))


# --- what the probes drew out survives into the briefing ------------------------------


def probe_and_answer(eng, answers, t_s=130):
    for answer in answers:
        assert eng.next_probe() is not None
        eng.note_caller(answer, t_s)
        t_s += 30


def test_a_probe_answer_is_kept_with_the_claim_it_answers(eng):
    """The answers were dropped, so a rolled session knew the project and not one thing
    the candidate had said about it."""
    eng.note_caller("we rewrote the payment reconciler after an outage", 100)
    probe_and_answer(eng, ["I wrote the advisory lock fix myself",
                           "it caused eleven double settlements in six weeks"])
    b = eng.briefing(200)
    assert len(eng.state.claims) == 1
    assert "their own part: I wrote the advisory lock fix myself" in b
    assert "the figure: it caused eleven double settlements in six weeks" in b


def test_a_fully_answered_ladder_fits_in_a_short_briefing(eng):
    for i, older in enumerate(["we moved billing to a queue in twelve weeks",
                               "I led the search index migration last year",
                               "we cut deploy time from forty minutes to six"]):
        eng.note_caller(older, 10 + i)
    eng.note_caller("we rewrote the payment reconciler after an outage", 100)
    answers = ["I wrote the advisory lock fix myself",
               "it caused eleven double settlements in six weeks",
               "we gave up some write throughput to the lock",
               "a nightly batch job deadlocked against it"]
    probe_and_answer(eng, answers)
    b = eng.briefing(400)
    for answer in answers:
        assert answer in b
    assert "deploy time" in b, "the newest older claim still fits"
    assert len(b.splitlines()) <= 10


def test_a_vague_probe_answer_is_not_briefed_as_substance(eng):
    eng.note_caller("we rewrote the payment reconciler after an outage", 100)
    probe_and_answer(eng, ["basically stuff like that"])
    assert "basically" not in eng.briefing(200)


def test_a_long_claim_keeps_the_figure_it_ends_on(eng):
    eng.note_caller("we rebuilt the payment reconciler after a painful outage last spring "
                    "and took p99 from 400 milliseconds down to 30", 100)
    assert "down to 30" in eng.briefing(200)


def test_a_shorter_call_moves_the_wrap_up(eng):
    short = InterviewEngine(call=CallConfig(max_duration_s=300, wrap_up_at_s=240))
    assert short.should_wrap_up(250)
    assert short.is_over(300)


def test_an_answer_to_a_probe_deepens_the_claim_rather_than_replacing_it(eng):
    """The bug this guards: every specific answer used to start a fresh claim, so the
    ladder reset on each turn and never got past its first rung."""
    eng.note_caller("we rewrote the payment reconciler after an outage", 100)
    assert eng.next_probe() == PROBE_LADDER[0]
    eng.note_caller("I wrote the advisory-lock fix myself", 110)
    assert len(eng.state.claims) == 1
    assert eng.next_probe() == PROBE_LADDER[1]


def test_probe_in_progress_tracks_the_descent(eng):
    assert not eng.probe_in_progress
    eng.note_caller("we rewrote the payment reconciler after an outage", 100)
    assert not eng.probe_in_progress
    eng.next_probe()
    assert eng.probe_in_progress


def test_probe_in_progress_clears_once_the_ladder_is_exhausted(eng):
    eng.note_caller("we rewrote the payment reconciler after an outage", 100)
    for _ in PROBE_LADDER:
        eng.next_probe()
        eng.note_caller("a specific sounding answer with numbers 42", 110)
    assert not eng.probe_in_progress


def test_a_spoken_number_makes_an_answer_specific(eng):
    """The engine used to require a digit, so an answer full of figures read as vague
    and the probe ladder stalled on a candidate who was being precise."""
    eng.note_caller("we saw about twelve hundred retries a second, you know", 100)
    assert eng.state.vague_streak == 0
    assert eng.state.claims


def test_the_final_rung_is_in_progress_until_the_candidate_answers_it(eng):
    """Issuing the last question used to count as finishing the ladder, so a rollover
    waiting for a finished ladder fired on that same turn and the question was lost."""
    eng.note_caller("we rewrote the payment reconciler after an outage", 100)
    for _ in PROBE_LADDER[:-1]:
        eng.next_probe()
        eng.note_caller("a specific answer with a number, 42", 110)

    assert eng.next_probe() == PROBE_LADDER[-1]
    assert eng.probe_in_progress, "the last question is out but not yet answered"

    eng.note_caller("a downstream report started double counting", 120)
    assert not eng.probe_in_progress
    assert eng.next_probe() is None


def test_a_ladder_the_engine_has_abandoned_is_not_in_progress(eng):
    """Two vague answers stop the questions, but the guard still reported the ladder
    as live. The rollover policy trusts that guard, so rollover stopped for good."""
    eng.note_caller("we rewrote the payment reconciler after an outage", 100)
    eng.next_probe()
    eng.note_caller("I wrote the advisory lock fix myself", 110)
    eng.next_probe()
    eng.note_caller("we basically did various things", 120)
    eng.next_probe()
    eng.note_caller("pretty much just stuff", 130)

    assert eng.next_probe() is None
    assert not eng.probe_in_progress, "the questions stopped but the guard says otherwise"
    assert eng.ladder_stalled
