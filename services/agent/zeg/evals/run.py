"""Run the labelled suite and report what a judge does with it.

Two things are being watched.

Agreement: how often the band matches what a human said. That is the number that decides
whether this is a product, and it is expected to be uncomfortable.

Spread: whether the judge discriminates at all. A judge that gives every candidate a 3
agrees with nothing and is the classic failure of model-as-judge. It looks fine on any
single report and is obvious across a suite, which is the whole reason this exists.
"""

from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from ..scoring import Assessment, Judge, score_call
from .fixtures import CASES, Case


@dataclass
class CaseResult:
    case: Case
    assessment: Assessment

    @property
    def agreed(self) -> bool:
        return self.assessment.band == self.case.expected_band

    @property
    def missing_evidence(self) -> List[str]:
        """Dimensions a human expected evidence for, that the judge found nothing on."""
        found = {d.dimension for d in self.assessment.dimensions if not d.insufficient}
        return [d for d in self.case.expect_evidence if d not in found]


@dataclass
class Report:
    results: List[CaseResult] = field(default_factory=list)

    @property
    def agreement(self) -> float:
        if not self.results:
            return 0.0
        return sum(1 for r in self.results if r.agreed) / len(self.results)

    @property
    def bands(self) -> Dict[str, int]:
        return dict(Counter(r.assessment.band for r in self.results))

    @property
    def scores(self) -> List[int]:
        return [r.assessment.overall for r in self.results
                if r.assessment.overall is not None]

    @property
    def compressed(self) -> bool:
        """True when the judge is not discriminating.

        Every scored call landing on one or two adjacent numbers means the rubric is
        decorative: the report looks confident and carries no information.
        """
        s = self.scores
        return len(s) >= 3 and (max(s) - min(s)) <= 1

    def render(self) -> str:
        out = ["%d cases, %.0f%% band agreement" % (len(self.results),
                                                    self.agreement * 100)]
        out.append("")
        for r in self.results:
            mark = "ok  " if r.agreed else "MISS"
            got = r.assessment.band
            score = "%d/10" % r.assessment.overall if r.assessment.overall else "  -  "
            out.append("  %s %-22s %s  %s" % (mark, r.case.name, score, got))
            if not r.agreed:
                out.append("       expected %s" % r.case.expected_band)
                out.append("       because  %s" % r.case.why)
            if r.missing_evidence:
                out.append("       no evidence found for: %s"
                           % ", ".join(r.missing_evidence))
        out.append("")
        out.append("band spread   %s" % self.bands)
        if self.scores:
            out.append("score range   %d to %d" % (min(self.scores), max(self.scores)))
        if self.compressed:
            out.append("WARNING       scores are compressed. The rubric is not "
                       "discriminating, so the reports carry no information.")
        return "\n".join(out)


def run_suite(judge: Optional[Judge] = None,
              cases: Sequence[Case] = CASES) -> Report:
    return Report([CaseResult(c, score_call(c.transcript, judge=judge)) for c in cases])


def main(argv=None) -> int:
    report = run_suite()
    print(report.render())
    # Deliberately not a failing exit code on low agreement. This is an instrument, and
    # a number that blocks a commit is a number people learn to game.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
