"""How gameable the scoring is, measured rather than asserted.

The bias eval's mirror: there, two answers say the same thing and must score the same.
Here, two calls sound the same and must not, because only one of them describes work that
happened. A candidate who talks like the rubric is the cheapest attack on a screening
tool, and it needs no tooling at all.

The heuristic judge cannot separate them, which its own docstring says plainly. That is
recorded below as a strict expected failure rather than hidden, so it turns into a real
failure the day a judge can tell the halves apart, and somebody has to come and delete it.
"""

import pytest

from zeg.evals.gaming import PAIRS, run_gaming


@pytest.mark.parametrize("pair", PAIRS, ids=lambda p: p.name)
def test_both_halves_of_a_pair_reach_a_score(pair):
    """A pair that scores nothing measures nothing, and would read as a pass.

    Three of the first four pairs written for this eval were two questions long and never
    reached the three scored dimensions a call needs, so every one of them looked fine.
    """
    from zeg.scoring import score_call

    assert score_call(pair.substantive).overall is not None
    assert score_call(pair.hollow).overall is not None


def test_the_halves_differ_only_in_substance():
    """Same questions, same first person, same certainty. If the hollow half were also
    shorter or vaguer in delivery, a judge could separate them on the wrong thing."""
    for pair in PAIRS:
        asked = [t.text for t in pair.substantive if t.speaker == "agent"]
        also_asked = [t.text for t in pair.hollow if t.speaker == "agent"]
        assert asked == also_asked, pair.name
        for turn in pair.hollow:
            if turn.speaker == "caller":
                assert turn.text.strip(), pair.name


def test_a_hollow_call_is_measured_against_a_real_one():
    report = run_gaming()
    assert not report.vacuous, report.render()
    assert len(report.results) == len(PAIRS)


@pytest.mark.xfail(strict=True, reason="the heuristic judge matches wording, so it cannot "
                                       "separate work from talk about work. Delete this "
                                       "marker when a judge closes the gap.")
def test_a_confident_empty_call_scores_below_a_real_one():
    """The measure this eval exists for: talk about work must not score like the work."""
    report = run_gaming()
    assert not report.unseparated, report.render()
