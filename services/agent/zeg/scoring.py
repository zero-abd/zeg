"""The post-call scoring pass.

Runs after the candidate hangs up, so latency is irrelevant and this pass can afford a
larger model, more sampling, and the whole transcript at once. None of that is true
during the call, which is why scoring is a separate stage rather than something the
conversational model is asked to do while talking.

Two rules shape the design, both from docs/05-scoring-and-reports.md.

Dimensions are scored independently, one judgement per call. Scoring all five together
lets one strong answer colour the rest, which is the halo effect reproduced in a model.

Evidence or it did not happen. A dimension with no citable span is recorded as
insufficient evidence, never as a low score. That distinction is what makes a report a
hiring manager can act on, and it is what makes an adverse decision defensible.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .engine import DIMENSIONS, Evidence

#: Rubric scores run 1 to 4. The headline number the recruiter sees is 1 to 10, which
#: is a presentation of the same judgement, not a finer one.
MIN_SCORE, MAX_SCORE = 1, 4

#: Below this many scored dimensions there is not enough to draw a conclusion from,
#: whatever the scored ones say.
MIN_SCORED_DIMENSIONS = 3


@dataclass
class QAUnit:
    """One question and the answer it drew, with timestamps kept."""

    question: str
    answer: str
    asked_at_s: float
    answered_at_s: float


@dataclass
class DimensionScore:
    dimension: str
    score: Optional[int]  # 1..4, or None for insufficient evidence
    evidence: List[Evidence] = field(default_factory=list)
    note: str = ""

    @property
    def insufficient(self) -> bool:
        return self.score is None


@dataclass
class Assessment:
    """What the recruiter reads."""

    overall: Optional[int]  # 1..10, or None when there is not enough signal
    band: str
    dimensions: List[DimensionScore]
    flags: List[str] = field(default_factory=list)
    duration_s: float = 0.0

    @property
    def insufficient_dimensions(self) -> List[str]:
        return [d.dimension for d in self.dimensions if d.insufficient]

    def render(self) -> str:
        """One page. A recruiter reads it in ninety seconds."""
        out = []
        headline = "%d/10" % self.overall if self.overall is not None else "no score"
        out.append("%s — %s" % (headline, self.band))
        out.append("")
        for d in self.dimensions:
            label = d.dimension.replace("_", " ")
            if d.insufficient:
                out.append("  %-18s insufficient evidence" % label)
            else:
                out.append("  %-18s %d/4" % (label, d.score))
            if d.evidence:
                e = d.evidence[0]
                m, s = divmod(int(e.at_s), 60)
                out.append('      [%02d:%02d] "%s"' % (m, s, _trim(e.quote)))
            elif d.note:
                out.append("      %s" % d.note)
        if self.flags:
            out.append("")
            out.append("Flags, for a human to weigh:")
            for f in self.flags:
                out.append("  - %s" % f)
        out.append("")
        out.append("A human reviews this before any decision. zeg does not decide.")
        return "\n".join(out)


# --- Turning a transcript into units -----------------------------------------


def to_qa_units(transcript: Sequence) -> List[QAUnit]:
    """Pair each agent question with the answer that followed it.

    Agent turns with no answer after them are dropped: an unanswered question is not
    evidence of anything, and the call ending is the usual reason for one.
    """
    units: List[QAUnit] = []
    pending = None
    for entry in transcript:
        if entry.speaker == "agent":
            pending = entry
        elif entry.speaker == "caller" and pending is not None:
            units.append(
                QAUnit(
                    question=pending.text,
                    answer=entry.text,
                    asked_at_s=pending.at_s,
                    answered_at_s=entry.at_s,
                )
            )
            pending = None
    return units


# --- Judging ------------------------------------------------------------------


class Judge:
    """Scores one dimension from the units that bear on it.

    Implementations: a deterministic heuristic used in tests and when no model is
    available, and a model-backed judge for real reports. Same contract, so a report
    produced either way has the same shape and the same evidence discipline.
    """

    name = "base"

    def score_dimension(self, dimension: str, units: Sequence[QAUnit]) -> DimensionScore:
        raise NotImplementedError


#: Signals of a specific, hard-to-fabricate answer. Deliberately shallow: this judge
#: exists so the pipeline is testable and demoable without a model, not to be good at
#: interviewing.
_NUMBER = re.compile(r"\b\d+(\.\d+)?\s*(ms|s|x|%|k|m|gb|mb|qps|rps|percent)?\b", re.I)
_CAUSAL = re.compile(r"\b(because|root cause|turned out|which meant|so that|due to)\b", re.I)
# Case-insensitive on purpose. Recognised speech is frequently lowercased, and a
# capital-I requirement silently loses every ownership claim in such a transcript.
_FIRST_PERSON = re.compile(
    r"\bi\s+(wrote|built|fixed|shipped|found|debugged|designed|owned|led|rewrote)\b", re.I
)
_TRADEOFF = re.compile(r"\b(gave up|traded|cost us|at the expense|downside|slower|doubled)\b", re.I)
_HYPOTHESIS = re.compile(r"\b(hypothes\w+|suspected|reproduced|repro|bisect|narrowed)\b", re.I)
_VAGUE = re.compile(r"\b(basically|stuff|things|various|pretty much|you know|a lot of)\b", re.I)

_SIGNALS: Dict[str, Sequence] = {
    "technical_depth": (_CAUSAL, _NUMBER),
    "ownership": (_FIRST_PERSON,),
    "tradeoffs": (_TRADEOFF,),
    "debugging": (_HYPOTHESIS,),
    "communication": (_CAUSAL,),
}


class HeuristicJudge(Judge):
    """A model-free judge. Deterministic, shallow, and honest about it.

    It scores on surface markers of specificity. It cannot tell a correct explanation
    from a confident wrong one, so it is for tests and offline runs. A report produced
    by this judge should never be shown to a hiring manager.
    """

    name = "heuristic"

    def score_dimension(self, dimension: str, units: Sequence[QAUnit]) -> DimensionScore:
        patterns = _SIGNALS.get(dimension, ())
        hits: List[Evidence] = []
        for u in units:
            if any(p.search(u.answer) for p in patterns):
                hits.append(Evidence(dimension, u.answer, u.answered_at_s))

        if not hits:
            return DimensionScore(
                dimension,
                None,
                [],
                "Nothing in the transcript speaks to this. Not a low score.",
            )

        vague = sum(1 for u in units if _VAGUE.search(u.answer))
        score = 2 + min(2, len(hits)) - (1 if vague > len(units) / 2 else 0)
        return DimensionScore(dimension, _clamp(score), hits)


def _clamp(n: int) -> int:
    return max(MIN_SCORE, min(MAX_SCORE, n))


# --- Putting it together -------------------------------------------------------


@dataclass
class RolePack:
    """Per-role weighting. Reviewed in pull requests, because changing one changes
    hiring outcomes."""

    name: str = "generic"
    weights: Dict[str, float] = field(
        default_factory=lambda: {d: 1.0 for d in DIMENSIONS}
    )


def score_call(
    transcript: Sequence,
    judge: Optional[Judge] = None,
    role: Optional[RolePack] = None,
    flags: Optional[Sequence[str]] = None,
) -> Assessment:
    """Transcript in, assessment out.

    Each dimension is judged on its own, from the units that bear on it, so one strong
    answer cannot lift the rest.
    """
    judge = judge or HeuristicJudge()
    role = role or RolePack()
    units = to_qa_units(transcript)
    duration = transcript[-1].at_s if len(transcript) else 0.0

    scores = [judge.score_dimension(d, units) for d in DIMENSIONS]
    scored = [s for s in scores if not s.insufficient]

    if len(scored) < MIN_SCORED_DIMENSIONS:
        return Assessment(
            overall=None,
            band="insufficient signal",
            dimensions=scores,
            flags=list(flags or ()) + [
                "Only %d of %d dimensions had citable evidence. Offer a human screen."
                % (len(scored), len(DIMENSIONS))
            ],
            duration_s=duration,
        )

    total_w = sum(role.weights.get(s.dimension, 1.0) for s in scored)
    weighted = sum(s.score * role.weights.get(s.dimension, 1.0) for s in scored)
    mean = weighted / total_w  # 1..4

    # 1..4 onto 1..10. The scale is presentation; the judgement is the rubric.
    overall = int(round((mean - MIN_SCORE) / (MAX_SCORE - MIN_SCORE) * 9 + 1))

    return Assessment(
        overall=overall,
        band=band_for(overall, scores),
        dimensions=scores,
        flags=list(flags or ()),
        duration_s=duration,
    )


def band_for(overall: int, scores: Sequence[DimensionScore]) -> str:
    """The recommendation, which is a band and not a verdict.

    "Advance with reservations" must be reachable and frequently used. A system that
    forces every call into advance or reject manufactures confidence it does not have.
    """
    thin = [s for s in scores if s.insufficient]
    if overall >= 8 and not thin:
        return "advance"
    if overall >= 6:
        return "advance with reservations"
    if overall >= 4:
        return "do not advance"
    return "do not advance"


def _trim(text: str, limit: int = 72) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
