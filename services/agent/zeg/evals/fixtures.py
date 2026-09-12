"""Hand-labelled calls.

Each case carries the band a careful human screener would reach, and why. The labels are
the point: they are what a change is measured against, so they are written to be
arguable rather than obvious. If the team disagrees with one, that disagreement is worth
more than the case.

These are synthetic. The real seed set is fifty recorded screens scored independently by
two engineers, and it is the expensive thing this project still owes. See
docs/05-scoring-and-reports.md.
"""

from dataclasses import dataclass, field
from typing import List, Sequence

from ..conversation import TranscriptEntry as T


@dataclass
class Case:
    name: str
    transcript: Sequence
    expected_band: str
    why: str
    #: Dimensions a human would expect to find evidence for. Used to catch a judge that
    #: scores everything rather than admitting it found nothing.
    expect_evidence: List[str] = field(default_factory=list)


STRONG = Case(
    name="strong_backend",
    expected_band="advance",
    why="Specific throughout, first-person, names a cost, remembers what broke.",
    expect_evidence=["technical_depth", "ownership", "tradeoffs", "debugging"],
    transcript=[
        T(0, "agent", "Tell me about the hardest bug you shipped a fix for this year."),
        T(12, "caller", "A race in our payment reconciler. Two workers could read the "
                        "same unsettled batch because the advisory lock was taken after "
                        "the read, not before."),
        T(30, "agent", "What did you personally do there?"),
        T(42, "caller", "I wrote the reproduction harness and the lock fix. Another "
                        "engineer reviewed it and did the backfill."),
        T(60, "agent", "Roughly how often was it firing?"),
        T(70, "caller", "Eleven double settlements over about six weeks, so under one a "
                        "day but each one needed a manual reversal."),
        T(88, "agent", "What did the fix cost you?"),
        T(100, "caller", "Reconciliation went from parallel to serial per merchant. "
                         "Batch time roughly doubled, from four minutes to nine."),
        T(120, "agent", "What broke afterwards that you did not expect?"),
        T(132, "caller", "A downstream report started double counting, because it had "
                         "been silently relying on the duplicate rows to join."),
    ],
)

MIXED = Case(
    name="mixed_ownership_unclear",
    expected_band="advance with reservations",
    why="Real detail about the system, but consistently 'we' and no cost named.",
    expect_evidence=["technical_depth"],
    transcript=[
        T(0, "agent", "Tell me about a recent project."),
        T(12, "caller", "We moved our ingestion pipeline from nightly batch to "
                        "streaming, because the nightly window stopped fitting."),
        T(30, "agent", "What did you personally do?"),
        T(40, "caller", "We split the work. I was across most of it."),
        T(55, "agent", "Any numbers on the improvement?"),
        T(64, "caller", "Latency went from hours to minutes. I do not have the exact "
                        "figures in front of me."),
        T(80, "agent", "What did you give up?"),
        T(88, "caller", "Not much really. It was better in every way."),
    ],
)

THIN = Case(
    name="thin_generic",
    expected_band="insufficient signal",
    why="Nothing specific enough to quote. Not a rejection; a human should screen.",
    transcript=[
        T(0, "agent", "Tell me about a recent project."),
        T(10, "caller", "We basically did a lot of various things with the backend."),
        T(24, "agent", "Anything specific you worked on?"),
        T(32, "caller", "Pretty much just general stuff, you know, the usual."),
        T(46, "agent", "What was hard about it?"),
        T(52, "caller", "It depends really. Things come up."),
    ],
)

DECLINED = Case(
    name="consent_declined",
    expected_band="insufficient signal",
    why="The call ended before anything was asked. Must never read as a rejection.",
    transcript=[
        T(0, "agent", "I am an AI interviewer and this call is recorded. Is that okay?"),
        T(8, "caller", "No, I would rather speak to a person."),
        T(14, "agent", "That is completely fine. Someone will reach out."),
    ],
)

SHORT_BUT_REAL = Case(
    name="short_but_real",
    expected_band="advance with reservations",
    why="Only two exchanges, but both are specific. Short is not the same as thin, "
        "and a judge that conflates them will reject people for a dropped connection.",
    expect_evidence=["ownership"],
    transcript=[
        T(0, "agent", "What did you work on most recently?"),
        T(10, "caller", "I rewrote our retry logic because we were hammering a "
                        "downstream service during partial outages."),
        T(28, "agent", "What changed?"),
        T(36, "caller", "I added jitter and a circuit breaker. Retry volume during the "
                        "next incident dropped by roughly ninety percent."),
    ],
)

#: A candidate who sounds impressive and says nothing checkable. The judge should not
#: reward fluency, and this is the case where it is most tempted to.
FLUENT_BUT_EMPTY = Case(
    name="fluent_but_empty",
    expected_band="insufficient signal",
    why="Articulate, confident, and entirely unfalsifiable. Fluency is not evidence.",
    transcript=[
        T(0, "agent", "Tell me about the hardest problem you have solved."),
        T(14, "caller", "I would say architecting resilient distributed systems at "
                        "scale. It is fundamentally about understanding the tradeoffs "
                        "inherent in consistency models."),
        T(36, "agent", "Can you give me a specific example?"),
        T(48, "caller", "Certainly. It really comes down to knowing your access "
                        "patterns and designing for failure from day one."),
    ],
)

CASES: Sequence[Case] = (
    STRONG,
    MIXED,
    THIN,
    DECLINED,
    SHORT_BUT_REAL,
    FLUENT_BUT_EMPTY,
)
