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
from .hesitation import is_hesitation
from .memory import shorten
from .textnorm import fold

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
                out.append('      [%02d:%02d] "%s"' % (m, s, excerpt(e.quote, d.dimension)))
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


def to_qa_units(transcript: Sequence, window: Optional[Sequence[float]] = None) -> List[QAUnit]:
    """Pair each agent question with the answer that followed it.

    Agent turns with no answer after them are dropped: an unanswered question is not
    evidence of anything, and the call ending is the usual reason for one.

    `window` is the interview itself, from consent to wrap-up. Only pairs whose question
    was asked inside it are kept. Without it, the recording disclosure and the wrap-up
    were paired like interview questions: a consent answer with a reason in it scored as
    technical depth, and a question the candidate asked at the end scored as ownership.
    """
    units: List[QAUnit] = []
    pending = None
    after_hesitation = False
    for entry in transcript:
        if entry.speaker == "agent":
            if pending is not None and after_hesitation and "?" not in entry.text:
                # Encouragement after a hesitation, like "take your time", is not a new
                # question. The question before it is still the one being answered.
                continue
            pending = entry
            after_hesitation = False
            continue
        if entry.speaker != "caller":
            continue
        if is_hesitation(entry.text):
            # A candidate thinking out loud has not answered. Taken as the answer, "um"
            # got the question and the real answer was paired with whatever came next.
            after_hesitation = after_hesitation or pending is not None
            continue
        after_hesitation = False
        if pending is not None:
            units.append(
                QAUnit(
                    question=pending.text,
                    answer=entry.text,
                    asked_at_s=pending.at_s,
                    answered_at_s=entry.at_s,
                )
            )
            pending = None
        elif units:
            # A candidate who pauses and then keeps going produces two turns in a row.
            # Dropping the second silently loses evidence, and the answer that follows
            # a pause is often the specific one, because they have had a moment to
            # remember the number.
            last = units[-1]
            units[-1] = QAUnit(
                question=last.question,
                answer="%s %s" % (last.answer, entry.text),
                asked_at_s=last.asked_at_s,
                answered_at_s=entry.at_s,
            )
    if window is not None:
        start, end = window
        units = [u for u in units if start <= u.asked_at_s < end]
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
#: People say numbers out loud, and recognition writes them down as words. A detector
#: that only sees digits misses "ninety percent", "twelve hundred" and "eleven double
#: settlements", which is every number the interview actually asks for.
#:
#: "one" is deliberately absent: "one of the things we did" is not a measurement, and a
#: false positive here inflates the score for an answer that gave no figure at all.
_NUMBER_WORDS = (
    r"two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
    r"fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|"
    r"seventy|eighty|ninety|hundred|thousand|million|billion"
)
_NUMBER = re.compile(
    r"\b\d+(\.\d+)?\s*(ms|s|x|%|k|m|gb|mb|qps|rps|percent)?\b"
    r"|\b(" + _NUMBER_WORDS + r")\b"
    r"|\b(percent|per cent|doubled|tripled|halved|quadrupled)\b",
    re.I,
)


def has_number(text: str) -> bool:
    """True when the text states a quantity, in digits or in words."""
    return bool(_NUMBER.search(text))
_CAUSAL = re.compile(r"\b(because|root cause|turned out|which meant|so that|due to)\b", re.I)
# Case-insensitive on purpose. Recognised speech is frequently lowercased, and a
# capital-I requirement silently loses every ownership claim in such a transcript.
_FIRST_PERSON = re.compile(
    r"\bi\s+(wrote|built|fixed|shipped|found|debugged|designed|owned|led|rewrote)\b", re.I
)
_TRADEOFF = re.compile(r"\b(gave up|traded|cost us|at the expense|downside|slower|doubled)\b", re.I)
_HYPOTHESIS = re.compile(r"\b(hypothes\w+|suspected|reproduced|repro|bisect|narrowed)\b", re.I)
#: Content-free words. "you know" and "um" are deliberately absent: they are filler,
#: which is delivery, not substance. Confusing the two cost a candidate three points in
#: the matched-pair evals.
_VAGUE = re.compile(r"\b(basically|stuff|things|various|pretty much|a lot of)\b", re.I)
#: Verbal filler. Not vagueness, and not weakness. It correlates with nervousness and
#: with speaking a second language, so anything that reads it as a lack of substance is
#: scoring the candidate's delivery. Stripped before any judgement is made.
_FILLER = re.compile(
    r"\b(u+m+|u+h+|e+r+m*|a+h+|you know|i mean|kind of|sort of)\b[,.]?\s*", re.I
)


def strip_filler(text: str) -> str:
    """Remove filler words. What is left is what the candidate actually said."""
    return " ".join(_FILLER.sub(" ", text).split())


#: Dashes a recogniser leaves where a speaker broke off. Hyphens inside a word are left
#: alone, because "advisory-lock" is one term and not a repair.
_BREAK = re.compile(r"[\u2014\u2013]+|(?<=\w)-(?=\s)")

#: An immediately repeated word. "I I wrote it" and "I I— wrote it" both say "I wrote
#: it"; the repetition is a disfluency, not content.
_REPETITION = re.compile(r"\b(\w+)\s+(?=\1\b)", re.I)


def strip_repairs(text: str) -> str:
    """Collapse stutters and self-corrections.

    Speech is full of these and a recogniser writes them down. Left in, they sit between
    a pronoun and its verb, which is exactly where the ownership signal lives: "I I—
    wrote the fix" stopped reading as first person at all, so a candidate claiming their
    own work was scored as having claimed nothing.
    """
    out = _BREAK.sub(" ", text)
    previous = None
    while previous != out:
        previous, out = out, _REPETITION.sub("", out)
    return " ".join(out.split())


def normalise(text: str) -> str:
    """What the candidate said, with delivery artefacts removed.

    Filler and repairs are how people talk, not how well they did the work. Everything
    that judges content runs on this; everything quoted back keeps their own words.
    """
    return strip_repairs(strip_filler(text))


_SIGNALS: Dict[str, Sequence] = {
    "technical_depth": (_CAUSAL, _NUMBER),
    "ownership": (_FIRST_PERSON,),
    "tradeoffs": (_TRADEOFF,),
    "debugging": (_HYPOTHESIS,),
    "communication": (_CAUSAL,),
}


def signals(text: str) -> List[str]:
    """Dimensions whose surface markers appear in what the candidate said.

    Shared with the interview engine, so what the live call counts as covered and what
    the heuristic judge scores cannot drift apart.
    """
    spoken = normalise(text)
    return [d for d, patterns in _SIGNALS.items() if any(p.search(spoken) for p in patterns)]


class HeuristicJudge(Judge):
    """A model-free judge. Deterministic, shallow, and honest about it.

    It scores on surface markers of specificity. It cannot tell a correct explanation
    from a confident wrong one, so it is for tests and offline runs. A report produced
    by this judge should never be shown to a hiring manager.
    """

    name = "heuristic"

    def score_dimension(self, dimension: str, units: Sequence[QAUnit]) -> DimensionScore:
        hits: List[Evidence] = []
        for u in units:
            # Judge the substance. The quote keeps the candidate's own words.
            if dimension in signals(u.answer):
                hits.append(Evidence(dimension, u.answer, u.answered_at_s))

        if not hits:
            return DimensionScore(
                dimension,
                None,
                [],
                "Nothing in the transcript speaks to this. Not a low score.",
            )

        # Vague means content-free, not containing a word from the list. Counting every
        # answer with "a lot of" or "things" in it took five specific answers from 9/10
        # to 6/10 when each opened with "There were a lot of things going on." That is
        # phrasing, not substance. The engine already judges vagueness this way.
        vague = sum(
            1 for u in units if _VAGUE.search(normalise(u.answer)) and not signals(u.answer)
        )
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
    window: Optional[Sequence[float]] = None,
) -> Assessment:
    """Transcript in, assessment out.

    Each dimension is judged on its own, from the units that bear on it, so one strong
    answer cannot lift the rest.
    """
    judge = judge or HeuristicJudge()
    role = role or RolePack()
    units = to_qa_units(transcript, window)
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


def excerpt(quote: str, dimension: str, limit: int = 72) -> str:
    """The part of a quote that is the evidence, in the candidate's own words.

    Quotes were cut from the end, and people lead in before they get to the point. Every
    quote in a realistic report stopped short of its evidence: the ownership line ended
    before "I wrote the advisory lock fix myself", so a recruiter saw a score and a
    lead-in. The window now sits on the earliest marker for the dimension, and a quote
    with none is shortened from the middle.
    """
    text = " ".join(quote.split())
    if len(text) <= limit:
        return text
    starts = [m.start() for m in (p.search(text) for p in _SIGNALS.get(dimension, ())) if m]
    if not starts:
        return shorten(text, limit)
    start = max(0, min(min(starts) - limit // 3, len(text) - limit))
    end = start + limit
    # Snap to whole words, so the window never opens or closes mid-word. A window with no
    # space to snap to is left as it is.
    if start > 0 and text[start - 1] != " ":
        space = text.find(" ", start, end)
        start = space + 1 if space != -1 else start
    if end < len(text) and text[end] != " ":
        space = text.rfind(" ", start, end)
        end = space if space != -1 else end
    return "%s%s%s" % ("…" if start > 0 else "", text[start:end].strip(),
                       "…" if end < len(text) else "")


# --- A judge with a model behind it -------------------------------------------

_DIMENSION_BRIEF = {
    "technical_depth": (
        "Does the candidate explain mechanisms correctly, and show awareness of how "
        "the thing fails? Specific causal explanations count. Naming technologies does "
        "not."
    ),
    "ownership": (
        "Did they do this, or were they nearby when it happened? First-person accounts "
        "carrying detail a bystander would not have are the evidence."
    ),
    "tradeoffs": (
        "Do they name what was given up, not only what was gained? Real work costs "
        "something and retellings often omit the cost."
    ),
    "debugging": (
        "Do they form a hypothesis before reaching for a fix? Reproducing, narrowing "
        "and isolating are the evidence."
    ),
    "communication": (
        "Do they structure an answer and adjust it when followed up? Score structure "
        "and responsiveness ONLY. Accent, fluency, pace, vocabulary breadth and "
        "grammatical correctness are irrelevant and must not affect this score."
    ),
}

JUDGE_PROMPT = """\
You are scoring one dimension of a technical screening interview. You are not making a
hiring decision and you are not scoring the whole candidate. Score only the dimension
named below.

Dimension: {dimension}
{brief}

Scoring: 1 is no evidence of this, 4 is strong evidence. If the transcript contains
nothing that speaks to this dimension, the score is null. A null is not a low score and
it is the correct answer far more often than people expect. Do not infer, do not give
the benefit of the doubt, and do not reward confidence.

Respond with JSON only:
{{"score": 1-4 or null, "quote": "verbatim span from the transcript, or null",
  "reason": "one sentence"}}

The quote must be copied exactly from the transcript below. A quote you cannot find
there is a fabrication and the answer is null instead.

Transcript:
{transcript}
"""


class ModelJudge(Judge):
    """Scores with a language model, one dimension per call.

    `complete` takes a prompt and returns the model's text. Keeping it a plain callable
    means this works against whatever is on the box without the scoring code knowing
    anything about it.

    The important behaviour here is distrust. A model asked for evidence will sometimes
    produce a quote that is not in the transcript, and a fabricated quote in a hiring
    report is worse than no report. Every citation is checked against the transcript
    verbatim, and one that is not found turns the whole verdict into insufficient
    evidence rather than being quietly dropped while the score survives.
    """

    name = "model"

    def __init__(self, complete, prompt: str = JUDGE_PROMPT) -> None:
        self.complete = complete
        self.prompt = prompt
        self.fabrications: List[str] = []

    def score_dimension(self, dimension: str, units: Sequence[QAUnit]) -> DimensionScore:
        if not units:
            return DimensionScore(dimension, None, [], "Nothing was said.")

        transcript = render_units(units)
        try:
            raw = self.complete(
                self.prompt.format(
                    dimension=dimension.replace("_", " "),
                    brief=_DIMENSION_BRIEF.get(dimension, ""),
                    transcript=transcript,
                )
            )
        except Exception as e:  # a judge that dies must not take the report with it
            return DimensionScore(dimension, None, [], "Judge failed: %s" % e)

        verdict = parse_verdict(raw)
        if verdict is None:
            return DimensionScore(
                dimension, None, [], "Judge returned something unreadable."
            )

        score, quote, reason = verdict
        if score is None:
            return DimensionScore(dimension, None, [], reason or "No evidence found.")

        if not quote or not _appears_in(quote, units):
            # The score might be right. It is not usable without a citation, and a
            # citation that cannot be located is the one thing a report must never
            # carry, so the score goes with it.
            self.fabrications.append(dimension)
            return DimensionScore(
                dimension,
                None,
                [],
                "Scored %s but cited a quote not present in the transcript." % score,
            )

        at = _timestamp_of(quote, units)
        return DimensionScore(
            dimension, _clamp(int(score)), [Evidence(dimension, quote, at)], reason
        )


def render_units(units: Sequence[QAUnit]) -> str:
    lines = []
    for u in units:
        lines.append("Interviewer: %s" % u.question)
        lines.append("Candidate: %s" % u.answer)
    return "\n".join(lines)


def parse_verdict(raw: str):
    """Pull (score, quote, reason) out of a model's reply, or None if unreadable.

    Tolerant of a model wrapping JSON in prose or a code fence, which they do. Not
    tolerant of anything it cannot parse: a guess here becomes a number in a hiring
    report.
    """
    import json

    if not isinstance(raw, str):
        return None
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(raw[start : end + 1])
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None

    score = data.get("score")
    if score is not None:
        try:
            score = int(score)
        except (TypeError, ValueError):
            return None
        if not MIN_SCORE <= score <= MAX_SCORE:
            return None

    quote = data.get("quote")
    if quote is not None and not isinstance(quote, str):
        return None
    reason = data.get("reason")
    return score, quote, reason if isinstance(reason, str) else ""


#: Punctuation a judge adds or drops when it quotes speech. Apostrophes inside words are
#: kept, so "didn't" and "did nt" stay different words.
_QUOTE_PUNCT = re.compile(r"[^\w\s']|(?<!\w)'|'(?!\w)")


def _normalise(text: str) -> str:
    """How a quote is compared: case, spacing, typography and punctuation ignored, words
    kept. Padded with spaces so a match is always of whole words.

    Genuine quotes were rejected, and the score voided, over a trailing full stop the
    transcript did not have or a straight apostrophe where recognition wrote a curly one.
    """
    words = _QUOTE_PUNCT.sub(" ", fold(text)).lower().split()
    return " %s " % " ".join(words) if words else ""


def _appears_in(quote: str, units: Sequence[QAUnit]) -> bool:
    """Whitespace and case are not fabrication; missing words are.

    Only the candidate's answers count. The interviewer's questions used to count too,
    so a judge citing "you personally do" from "What did you personally do?" scored the
    candidate 4 on ownership with the interviewer's own words as the evidence.
    """
    needle = _normalise(quote)
    if not needle:
        return False
    return any(needle in _normalise(u.answer) for u in units)


def _timestamp_of(quote: str, units: Sequence[QAUnit]) -> float:
    needle = _normalise(quote)
    for u in units:
        if needle in _normalise(u.answer):
            return u.answered_at_s
    return 0.0
