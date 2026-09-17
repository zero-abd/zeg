"""Matched pairs: same surface, different substance.

The mirror of the bias eval. There, two answers say the same thing and must score the
same. Here, two answers sound the same and must not: one carries what the rubric asks
for, the other carries the wording of it and nothing else. "I single-handedly designed,
built and delivered the whole platform myself" has every ownership marker in the list and
names nothing that was built.

This is the measure of how gameable the scoring is. A judge that cannot separate these
halves can be talked into an advance by a confident candidate who did none of the work,
which is the failure mode a screening tool has to be honest about. The heuristic judge
cannot separate them at all, and says so in its own docstring; the gap below is what a
model judge has to close, and the number is what says whether it did.

Run it against whatever judge is being considered. The verdict is the size of the gap,
not a pass or a fail.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from ..conversation import TranscriptEntry as T
from ..scoring import Judge, score_call


@dataclass
class Pair:
    name: str
    what_differs: str
    #: The answers that carry evidence: a named thing, a figure, a cost that was paid.
    substantive: Sequence
    #: The answers that carry only the wording of evidence.
    hollow: Sequence


def _qa(*pairs):
    """Build a transcript from (question, answer) pairs on a fixed clock."""
    out, t = [], 0
    for question, answer in pairs:
        out.append(T(t, "agent", question))
        out.append(T(t + 10, "caller", answer))
        t += 30
    return out


#: Each half is a whole call, because a pair that does not reach a score measures nothing.
#: Both halves are first person, both sound certain, both use the rubric's own vocabulary
#: across all five dimensions. Only one of them could be checked by someone who was there.
RECONCILER = Pair(
    name="a_race_in_the_reconciler",
    what_differs="Both claim the fix. One names the lock, the figures and what it cost.",
    substantive=_qa(
        ("Tell me about the hardest bug you fixed.",
         "A race in our payment reconciler: two workers could read the same unsettled "
         "batch, because the advisory lock was taken after the read instead of before."),
        ("What did you personally do?",
         "I wrote the lock fix myself, and the repro harness that proved it."),
        ("Any numbers?",
         "Eleven double settlements over six weeks, and p99 went from 900 ms to 40 ms."),
        ("What did it cost?",
         "We gave up parallel reconciliation, so batch time roughly doubled to two hours."),
        ("How did you find it?",
         "I reproduced it under load and narrowed it to one merchant, then read the lock "
         "ordering and saw the read came first."),
    ),
    hollow=_qa(
        ("Tell me about the hardest bug you fixed.",
         "A really fundamental architectural issue in our payments layer that I owned."),
        ("What did you personally do?",
         "I personally drove the whole thing myself, end to end, single-handedly."),
        ("Any numbers?",
         "I improved performance by 100x and cut latency by 90 percent across the board."),
        ("What did it cost?",
         "Nothing really, because I optimised the tradeoff away completely."),
        ("How did you find it?",
         "I debugged it because the root cause was obvious to me straight away."),
    ),
)

MIGRATION = Pair(
    name="a_migration_off_a_shared_database",
    what_differs="Both claim the migration. One says what moved, in what order, and what broke.",
    substantive=_qa(
        ("Tell me about a project you are proud of.",
         "Moving billing off the shared database, because a long report could lock the "
         "table that took payments."),
        ("What did you personally do?",
         "I wrote the dual-write path and the backfill myself, and ran the cutover."),
        ("Any numbers?",
         "Four tables, about 40 million rows, cut over in three batches over two weeks."),
        ("What did it cost?",
         "We ran both writes for a fortnight, so every write cost twice as much."),
        ("What broke afterwards?",
         "A report still pointed at the old table for a day, because I missed one config "
         "key, which is why we kept the dual write on."),
    ),
    hollow=_qa(
        ("Tell me about a project you are proud of.",
         "A complete end-to-end re-architecture of our entire data layer that I led."),
        ("What did you personally do?",
         "I took full ownership of all of it and delivered the whole thing myself."),
        ("Any numbers?",
         "We were handling a massive scale, easily thousands and thousands of operations."),
        ("What did it cost?",
         "Honestly there was no real downside, it was strictly better in every dimension."),
        ("What broke afterwards?",
         "Nothing at all broke, because I had thought through every edge case up front."),
    ),
)

PAIRS: Sequence[Pair] = (RECONCILER, MIGRATION)


@dataclass
class PairResult:
    name: str
    what_differs: str
    substantive: Optional[int]
    hollow: Optional[int]

    @property
    def gap(self) -> Optional[int]:
        """How much the hollow half scored below the substantive one.

        None when either half went unscored: a pair that produces no score measures
        nothing, and reading that as a pass would be the same mistake this eval exists
        to catch.
        """
        if self.substantive is None or self.hollow is None:
            return None
        return self.substantive - self.hollow

    @property
    def separated(self) -> bool:
        return (self.gap or 0) > 0


@dataclass
class GamingReport:
    results: List[PairResult] = field(default_factory=list)

    @property
    def unseparated(self) -> List[PairResult]:
        return [r for r in self.results if not r.separated]

    @property
    def vacuous(self) -> List[PairResult]:
        return [r for r in self.results if r.gap is None]

    def render(self) -> str:
        out = ["%d pairs, same surface, different substance" % len(self.results), ""]
        for r in self.results:
            mark = "ok  " if r.separated else "SAME"
            out.append("  %s %-34s substance %s vs wording %s%s"
                       % (mark, r.name, _n(r.substantive), _n(r.hollow),
                          "   (nothing scored)" if r.gap is None else ""))
        out.append("")
        if self.vacuous:
            out.append("verdict       %d pairs scored nothing, so they measure nothing"
                       % len(self.vacuous))
        elif self.unseparated:
            out.append("verdict       %d of %d pairs scored the wording as highly as the work"
                       % (len(self.unseparated), len(self.results)))
        else:
            out.append("verdict       every pair scored the work above the wording")
        out.append("")
        out.append("A candidate who talks like the rubric is the cheapest attack on this "
                   "system, and it needs no tooling.")
        return "\n".join(out)


def _n(value) -> str:
    return "-" if value is None else "%d/10" % value


def run_gaming(judge: Optional[Judge] = None,
               pairs: Sequence[Pair] = PAIRS) -> GamingReport:
    """Score both halves of every pair with one judge."""
    report = GamingReport()
    for pair in pairs:
        report.results.append(PairResult(
            pair.name,
            pair.what_differs,
            score_call(pair.substantive, judge=judge).overall,
            score_call(pair.hollow, judge=judge).overall,
        ))
    return report
