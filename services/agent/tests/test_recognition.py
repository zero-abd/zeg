"""Scoring an imperfect transcript.

Everything the scorer was fed before this was written by hand and punctuated correctly.
Nothing on the box will look like that.

This is not a general robustness concern. docs/05 names the most probable route to a
discriminatory outcome: recognition is worse on some accents, the scorer sees a degraded
version of what was said, and the transcription gap becomes a scoring gap. A candidate
is then marked down for how clearly the machine heard them.
"""

import pytest

from zeg.evals.recognition import (
    CLEAN,
    DEGRADATIONS,
    degrade,
    dropped_articles,
    hesitation_repair,
    run_recognition,
    stutter,
    unpunctuated,
)
from zeg.scoring import normalise, score_call, strip_repairs


def test_no_degradation_moves_the_score():
    r = run_recognition()
    assert r.held, r.render()
    assert r.worst_loss == 0


@pytest.mark.parametrize("name,fn", DEGRADATIONS, ids=[n for n, _ in DEGRADATIONS])
def test_each_degradation_holds(name, fn):
    clean = score_call(CLEAN)
    got = score_call(degrade(CLEAN, fn))
    assert got.overall == clean.overall, name
    assert got.band == clean.band, name


def test_the_clean_transcript_actually_scores():
    """If the baseline scored nothing, every comparison above would be vacuous."""
    assert score_call(CLEAN).overall is not None


def test_only_the_candidate_is_degraded():
    """The agent's words are synthesised by us and arrive intact. Only what was heard
    is imperfect, which is the asymmetry the real system has."""
    degraded = degrade(CLEAN, unpunctuated)
    agent_clean = [e.text for e in CLEAN if e.speaker == "agent"]
    agent_degraded = [e.text for e in degraded if e.speaker == "agent"]
    assert agent_clean == agent_degraded


# --- the bug this found ---------------------------------------------------------


def test_a_self_correction_does_not_destroy_the_ownership_signal():
    """The repair sits between the pronoun and its verb, which is exactly where
    ownership lives. "I I— wrote the fix" stopped reading as first person at all, so a
    candidate claiming their own work scored as having claimed nothing."""
    degraded = degrade(CLEAN, hesitation_repair)
    own = next(d for d in score_call(degraded).dimensions if d.dimension == "ownership")
    assert not own.insufficient


@pytest.mark.parametrize("said,meant", [
    ("I I— wrote the fix", "I wrote the fix"),
    ("I I wrote the fix", "I wrote the fix"),
    ("A A— race in the reconciler", "A race in the reconciler"),
    ("we we we rebuilt it", "we rebuilt it"),
])
def test_stutters_and_repairs_collapse(said, meant):
    assert strip_repairs(said) == meant


def test_a_hyphenated_term_is_not_a_repair():
    """"advisory-lock" is one term. Treating the hyphen as a break would split it."""
    assert strip_repairs("the advisory-lock fix") == "the advisory-lock fix"


def test_filler_and_repairs_are_removed_together():
    assert normalise("um I I wrote the fix, you know").startswith("I wrote the fix")


def test_normalising_leaves_clean_speech_alone():
    clean = "I reproduced it under load and narrowed it to one merchant"
    assert normalise(clean) == clean


# --- the instrument -------------------------------------------------------------


def test_the_report_names_a_degradation_that_lost_points():
    from zeg.evals.recognition import RecognitionReport, RecognitionResult

    lost = RecognitionResult("stutter", 8, 5, "advance", "do not advance")
    text = RecognitionReport([lost], 8).render()
    assert "LOST" in text
    assert "how clearly the machine heard them" in text


def test_a_dimension_that_moved_is_a_loss_even_when_the_overall_holds():
    """The matched-pair eval missed filler costing ownership because it compared only
    the overall score. This instrument had the same blind spot."""
    from zeg.evals.recognition import RecognitionReport, RecognitionResult

    clean = {"technical_depth": 4, "ownership": 4, "tradeoffs": 3, "debugging": 4,
             "communication": 3}
    degraded = dict(clean, ownership=3, tradeoffs=4)  # same mean, same overall
    r = RecognitionResult("stutter", 9, 9, "advance", "advance",
                          clean_dimensions=clean, degraded_dimensions=degraded)
    assert not r.held
    text = RecognitionReport([r], 9).render()
    assert "ownership moved: 4 -> 3" in text
    assert "does not move the score" not in text


def test_a_judge_that_scores_nothing_is_not_a_clean_bill_of_health():
    """Nothing equals nothing. The report said recognition quality did not move the
    score, about a judge that never produced one."""
    from zeg.scoring import DimensionScore, Judge

    class NoEvidence(Judge):
        def score_dimension(self, dimension, units):
            return DimensionScore(dimension, None, [], "nothing")

    report = run_recognition(judge=NoEvidence())
    assert not report.held
    assert "inconclusive" in report.render()


@pytest.mark.parametrize("name,fn", DEGRADATIONS, ids=[n for n, _ in DEGRADATIONS])
def test_each_degradation_holds_on_every_dimension(name, fn):
    clean = {d.dimension: d.score for d in score_call(CLEAN).dimensions}
    got = {d.dimension: d.score for d in score_call(degrade(CLEAN, fn)).dimensions}
    assert got == clean, name


def test_degradations_actually_change_the_text():
    """A degradation that is a no-op tests nothing."""
    for name, fn in DEGRADATIONS:
        answer = next(e.text for e in CLEAN if e.speaker == "caller")
        assert fn(answer) != answer, name
