"""Matched pairs: same substance, different delivery.

The most likely way this system discriminates is scoring how someone sounds. These
tests are the guard, and one of them is a regression: verbal filler alone used to cost a
candidate three points and move them from advance to reject.
"""

import pytest

from zeg.evals.bias import PAIRS, BiasReport, PairResult, run_pairs
from zeg.scoring import DimensionScore, Judge, strip_filler


class Flat(Judge):
    def score_dimension(self, dimension, units):
        return DimensionScore(dimension, 3, [])


class NoEvidence(Judge):
    def score_dimension(self, dimension, units):
        return DimensionScore(dimension, None, [], "nothing")


# --- the regression -----------------------------------------------------------


def test_verbal_filler_does_not_change_the_score():
    """The bug: um, uh and you know were being read as vagueness, which dropped the
    candidate from advance with reservations to do not advance on identical facts."""
    r = next(x for x in run_pairs().results if x.pair.name == "verbal_filler")
    assert r.clean, "filler moved the score from %s to %s" % (
        r.baseline_score, r.variant_score)


def test_no_pair_shows_a_score_difference():
    report = run_pairs()
    assert report.clean, report.render()
    assert report.worst_delta == 0


@pytest.mark.parametrize("name", [p.name for p in PAIRS])
def test_each_pair_is_individually_clean(name):
    r = next(x for x in run_pairs().results if x.pair.name == name)
    assert r.clean, r.pair.what_differs


# --- filler is delivery, not substance ------------------------------------------


@pytest.mark.parametrize("text,expected", [
    ("um I wrote the fix", "I wrote the fix"),
    ("I wrote it, you know, myself", "I wrote it, myself"),
    ("uh, the root cause was a lock", "the root cause was a lock"),
    ("I mean we doubled throughput", "we doubled throughput"),
])
def test_filler_is_stripped(text, expected):
    assert strip_filler(text) == expected


def test_stripping_leaves_real_content_alone():
    real = "The root cause was a race between two workers"
    assert strip_filler(real) == real


def test_vagueness_survives_stripping():
    """Filler is not vagueness, but vagueness must still be caught."""
    assert "stuff" in strip_filler("um, we basically did stuff, you know")


# --- the instrument itself --------------------------------------------------------


def test_a_pair_that_scores_nothing_on_either_half_is_not_clean():
    """An equality check over two nulls passes while proving nothing, and a suite full
    of them reads as a clean bill of health."""
    report = run_pairs(judge=NoEvidence())
    assert all(r.vacuous for r in report.results)
    assert not report.clean


def test_a_vacuous_run_says_inconclusive_not_pass():
    assert "inconclusive" in run_pairs(judge=NoEvidence()).render()


def test_every_baseline_actually_scores():
    """If a baseline cannot score, its pair measures nothing."""
    for r in run_pairs().results:
        assert r.baseline_score is not None, r.pair.name


def test_a_difference_is_reported_with_what_differed():
    result = PairResult(PAIRS[0], 7, 4, "advance with reservations", "do not advance")
    text = BiasReport([result]).render()
    assert "BIAS" in text
    assert PAIRS[0].what_differs in text


def test_the_pairs_differ_only_in_delivery():
    """A pair whose halves make different claims measures nothing about bias."""
    for p in PAIRS:
        assert len(p.baseline) == len(p.variant), p.name


def test_a_flat_judge_is_clean_but_that_proves_nothing():
    """Worth knowing: this suite cannot detect bias in a judge that ignores content."""
    assert run_pairs(judge=Flat()).clean
