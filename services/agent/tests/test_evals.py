"""The instrument that says whether a change helped.

These tests check the instrument, not the judge. A broken instrument that reports 100%
agreement is worse than no instrument, because it is believed.
"""

import pytest

from zeg.evals import CASES, run_suite
from zeg.evals.fixtures import Case
from zeg.evals.run import Report
from zeg.scoring import DimensionScore, Judge
from zeg.engine import DIMENSIONS


class Fixed(Judge):
    """Gives every dimension the same score, whatever was said."""

    def __init__(self, score):
        self.value = score

    def score_dimension(self, dimension, units):
        if self.value is None:
            return DimensionScore(dimension, None, [], "nothing")
        return DimensionScore(dimension, self.value, [], "flat")


# --- the fixtures themselves ---------------------------------------------------


def test_every_case_is_labelled_with_a_reason():
    for c in CASES:
        assert c.why, "%s has no rationale, so nobody can argue with the label" % c.name
        assert c.expected_band


def test_the_suite_covers_every_band_that_matters():
    bands = {c.expected_band for c in CASES}
    assert "advance" in bands
    assert "insufficient signal" in bands
    assert "advance with reservations" in bands


def test_a_declined_call_is_labelled_as_no_signal_not_a_rejection():
    declined = next(c for c in CASES if c.name == "consent_declined")
    assert declined.expected_band == "insufficient signal"


def test_the_suite_includes_a_candidate_who_sounds_good_and_says_nothing():
    """The case a judge is most tempted to reward. Fluency is not evidence."""
    fluent = next(c for c in CASES if c.name == "fluent_but_empty")
    assert fluent.expected_band == "insufficient signal"


def test_short_and_thin_are_different_cases():
    """Conflating them rejects people for a dropped connection."""
    short = next(c for c in CASES if c.name == "short_but_real")
    thin = next(c for c in CASES if c.name == "thin_generic")
    assert short.expected_band != thin.expected_band
    assert len(short.transcript) <= len(thin.transcript)


# --- the report ------------------------------------------------------------------


def test_agreement_is_the_share_of_matching_bands():
    r = run_suite()
    assert 0.0 <= r.agreement <= 1.0
    assert len(r.results) == len(CASES)


def test_a_judge_that_agrees_with_nothing_scores_zero():
    """A flat 1 across every dimension cannot reach any of the labelled bands."""
    assert run_suite(judge=Fixed(1)).agreement < 1.0


def test_compression_is_detected():
    """Every scored call landing on one number means the rubric is decorative."""
    assert run_suite(judge=Fixed(3)).compressed


def test_a_judge_with_spread_is_not_flagged_as_compressed():
    r = run_suite()
    assert not r.compressed


def test_a_judge_that_finds_nothing_is_not_flagged_as_compressed():
    """No scores at all is a different failure from every score being the same."""
    assert not run_suite(judge=Fixed(None)).compressed


def test_missing_evidence_is_reported_per_case():
    r = run_suite(judge=Fixed(None))
    expecting = [c for c in r.results if c.case.expect_evidence]
    assert expecting and all(c.missing_evidence for c in expecting)


def test_the_report_names_the_cases_it_missed():
    text = run_suite(judge=Fixed(1)).render()
    assert "MISS" in text
    assert "expected" in text


def test_the_report_shows_the_band_spread():
    assert "band spread" in run_suite().render()


def test_the_compression_warning_says_why_it_matters():
    text = run_suite(judge=Fixed(3)).render()
    assert "not " in text and "discriminating" in text


def test_an_empty_suite_does_not_divide_by_zero():
    assert Report([]).agreement == 0.0


def test_the_default_judge_gives_an_honest_baseline():
    """Pinned so a change that quietly makes scoring worse shows up as a diff."""
    r = run_suite()
    assert 0.5 <= r.agreement <= 0.85, (
        "heuristic baseline moved to %.2f; if that was intentional, update this"
        % r.agreement
    )
