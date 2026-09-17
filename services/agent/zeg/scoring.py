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

import math
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .asks import is_question
from .engine import DIMENSIONS, Evidence
from .hesitation import is_hesitation
from .memory import shorten
from .prompts import INTERJECTIONS
from .textnorm import fold
from .withdrawal import reads_as_withdrawal, wants_a_human

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
    #: Which judge produced this. A heuristic report and a model-judged one rendered
    #: identically, so "9/10 — advance" from a judge that only matches wording looked
    #: exactly like a real assessment.
    judge: str = ""

    @property
    def insufficient_dimensions(self) -> List[str]:
        return [d.dimension for d in self.dimensions if d.insufficient]

    def justification(self) -> str:
        """The one sentence under the band, and how long the call was.

        The format the docs ask for is "the recommendation band and the single sentence
        that justifies it", and the band stood alone. Built from the scores themselves
        rather than from a model, so it cannot say anything the rubric does not.
        """
        strong = [d.dimension for d in self.dimensions if d.score is not None and d.score >= 3]
        weak = [d.dimension for d in self.dimensions if d.score is not None and d.score <= 2]
        thin = self.insufficient_dimensions
        parts = []
        if strong:
            parts.append("evidence for %s" % _names(strong))
        if weak:
            parts.append("little for %s" % _names(weak))
        if thin:
            parts.append("nothing on %s" % _names(thin))
        mins, secs = divmod(int(self.duration_s), 60)
        sentence = "; ".join(parts) if parts else "nothing scorable was said"
        return "%s%s. Call length %d:%02d." % (sentence[0].upper(), sentence[1:], mins, secs)

    def render(self) -> str:
        """One page. A recruiter reads it in ninety seconds."""
        out = []
        headline = "%d/10" % self.overall if self.overall is not None else "no score"
        out.append("%s — %s" % (headline, self.band))
        if self.judge == "heuristic":
            # Its own documentation says a report from this judge must never be shown to
            # a hiring manager. The report did not say which judge produced it, so the
            # warning never reached anyone reading one.
            out.append(
                "Scored by the heuristic judge, which matches wording rather than judging "
                "answers. For testing only: not for a hiring decision."
            )
        elif self.judge:
            out.append("Scored by the %s judge." % self.judge)
        out.append(self.justification())
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


def _names(dimensions: Sequence[str]) -> str:
    """Dimension names as a reader would say them: a, b and c."""
    plain = [d.replace("_", " ") for d in dimensions]
    if len(plain) == 1:
        return plain[0]
    return "%s and %s" % (", ".join(plain[:-1]), plain[-1])


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
            if pending is not None and entry.text in INTERJECTIONS:
                # A nudge such as "Take your time" is not a new question. The one before
                # it is still what the candidate is answering.
                continue
            if pending is not None and after_hesitation and "?" not in entry.text:
                # Encouragement after a hesitation, like "take your time", is not a new
                # question. The question before it is still the one being answered.
                continue
            pending = entry
            after_hesitation = False
            continue
        if entry.speaker != "caller":
            continue
        # Asking to stop, or for a person, is not an answer to anything. Paired as one, the
        # judge was shown "What tradeoff did you accept?" answered by "I'd rather speak to a
        # person", and a low score citing it passed the quote check because it was quoted
        # exactly. The flag on the record is where that request belongs.
        if reads_as_withdrawal(entry.text) or wants_a_human(entry.text):
            continue
        # A candidate asking something back has not answered either. It was paired as the
        # answer, and their real answer was then paired with the interviewer's reply to
        # their question. The same rule the interview applies live.
        if is_hesitation(entry.text) or (is_question(entry.text) and not signals(entry.text)):
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
    r"|\b(percent|per cent|doubled|doubles|tripled|triples|halved|quadrupled)\b"
    # Quantities said without a number: "twice a week", "half the batches", "tenfold".
    # "half" only with something it is half of, so "the second half of the call" is not one.
    r"|\b(twice|thrice|dozens?|(two|three|four|five|ten|hundred)fold)\b"
    r"|(?<!second\s)(?<!first\s)\bhalf\s+(the|of|our|all|a|an)\b",
    re.I,
)


def has_number(text: str) -> bool:
    """True when the text states a quantity, in digits or in words."""
    return bool(_NUMBER.search(text))
#: An explanation of why, not only what. Three of ten ordinary causal explanations were
#: recognised: "which caused the double settlements", "as a result", "the reason was" and
#: "that is why" all counted for nothing. "since" is deliberately absent: "since March"
#: is about time, and a word that means cause half the time is not evidence of it.
_CAUSAL = re.compile(
    r"\b(because|root cause|turned out|which meant|so that|due to|caused|causes|led to"
    r"|leads to"
    r"|as a result|the reason (was|is)|that'?s why|that is why|which is why"
    r"|the problem was that|the issue was that|which made)\b",
    re.I,
)
#: An answer with a shape: a sequence, a count of parts, a direct answer first. The
#: communication brief is structure and responsiveness, yet only causal words were ever
#: checked, so "first we reproduced it, then we added the lock, and finally we
#: backfilled" earned nothing for communication.
_STRUCTURE = re.compile(
    # "after is" and "afterwards" as well as "after that": "First is the lock, after is the
    # backfill" lost communication. Not a bare "after", which is as often about time.
    r"\bfirst(ly)?\b[^.?!]{0,80}\b(then|second(ly)?|next|after (that|this|is|was)|afterwards"
    r"|finally)\b"
    r"|\b(two|three|four|a couple of|a few) (parts|steps|stages|reasons|pieces|things)\b"
    r"|\bstep (one|two|1|2)\b|\bshort version\b|\bin short\b"
    r"|\bto answer your question\b",
    re.I,
)
# Case-insensitive on purpose. Recognised speech is frequently lowercased, and a
# capital-I requirement silently loses every ownership claim in such a transcript.
#: Verbs an engineer uses to say they did the work. The list was ten long and required the
#: verb to follow "I" directly, so of twelve first-person claims only two counted, and the
#: natural answer to the engine's own probe — "I personally rewrote the reconciler" —
#: counted as no ownership at all. Two candidates claiming the same work in different
#: words scored differently, which is scoring vocabulary, not ownership.
def _tenses(regular, irregular) -> str:
    """Every tense of each verb, as one alternation.

    The lists were past tense only. "I've written the fix" and "I write the fix" both
    scored ownership as nothing, where "I wrote the fix" scored 4, and narrating past work
    in the present is especially common in non-native speech. A tense is how someone talks,
    not what they did.
    """
    forms = set()
    for verb in regular:
        head, _, tail = verb.partition(" ")
        tail = " " + tail if tail else ""
        if head.endswith("e"):
            stems = (head, head + "s", head + "d")
        elif head.endswith(("s", "sh", "ch", "x", "z")):
            stems = (head, head + "es", head + "ed")
        else:
            stems = (head, head + "s", head + "ed")
        forms.update(stem + tail for stem in stems)
    for group in irregular:
        forms.update(group)
    return "|".join(sorted(forms, key=len, reverse=True))


_OWNERSHIP_VERBS = _tenses(
    regular=(
        "fix", "design", "redesign", "own", "implement", "add", "refactor", "migrate",
        "introduce", "propose", "profile", "diagnose", "trace", "reproduce", "architect",
        "deploy", "roll out", "create", "develop", "author", "replace", "remove",
        "optimize", "optimise", "tune", "benchmark", "instrument", "automate",
        "investigate", "wire up", "patch",
        # First-person investigative work, like "reproduce" and "trace". "I isolated it"
        # counted as debugging but not ownership while "I reproduced it" counted as both.
        "isolate", "narrow", "rule out", "bisect", "measure",
    ),
    irregular=(
        ("write", "writes", "wrote", "written"),
        ("rewrite", "rewrites", "rewrote", "rewritten"),
        ("build", "builds", "built"),
        ("rebuild", "rebuilds", "rebuilt"),
        ("lead", "leads", "led"),
        ("ship", "ships", "shipped"),
        ("debug", "debugs", "debugged"),
        ("set up", "sets up"),
        # Past forms only. "I find it hard", "I run into this", "I drive to work" are not
        # claims of having done the work.
        ("found",), ("drove", "driven"), ("ran",),
    ),
)
#: Words that sit between "I" and the verb without changing who did it. "basically" is
#: deliberately absent: it is on the vagueness list and should not open a door here.
_BETWEEN = r"personally|actually|myself|then|also|just|eventually|finally|really|first|later|mostly"
#: "I've written", "I have reproduced", "I had built". Not "I'd", which is as often "I
#: would" as "I had", and "I'd rewrite it differently" is not a claim of having done it.
_AUXILIARY = r"(?:'ve|'m|\s+have|\s+had|\s+am|\s+was)?"

#: An answer that starts with the verb, the pronoun dropped: "Rewrote the settlement worker
#: myself." Common in terse speech and from speakers of languages that drop subject
#: pronouns, and it scored ownership as nothing. Past forms only, so an imperative is not
#: a claim; never followed by "by", so "Built by the platform team" is not either. "found",
#: "ran" and "led" are left out: "Found out later", "Ran into a deadlock", "Led to
#: duplicate payments" are not claims of doing the work.
_DROPPED_SUBJECT_PAST = (
    r"rewrote|rewritten|wrote|written|built|rebuilt|fixed|shipped|debugged|designed"
    r"|redesigned|implemented|added|refactored|migrated|introduced|proposed|profiled"
    r"|diagnosed|traced|reproduced|architected|deployed|rolled out|created|developed"
    r"|authored|replaced|removed|optimi[sz]ed|tuned|benchmarked|instrumented|automated"
    r"|investigated|wired up|patched|isolated|narrowed|ruled out|bisected|set up"
)
_FIRST_PERSON = re.compile(
    r"\bi" + _AUXILIARY + r"\s+(?:(?:" + _BETWEEN + r")\s+){0,2}(?:" + _OWNERSHIP_VERBS + r")\b"
    # A dropped subject is as often "we" as "I", so it counts only when the sentence says
    # whose work it was: "Rewrote the settlement worker myself", "Personally rewrote it".
    # Crediting every one over-credited "Isolated it to one merchant", said about a team.
    + r"|(?:^|[.!?;]\s+)personally\s+(?:" + _DROPPED_SUBJECT_PAST + r")\b"
    + r"|(?:^|[.!?;]\s+)(?:(?:and|so|then|also|just|actually)\s+)?"
    + r"(?:" + _DROPPED_SUBJECT_PAST + r")\b(?!\s+(?:by|income)\b)(?=[^.!?]*\bmyself\b)"
    # Clefts and passives: "It was me who rewrote it", "I'm the one who rewrote it", "The
    # worker was rewritten by me". Each scored no ownership.
    + r"|\b(?:i\s+(?:was|am)|i'm)\s+the\s+one\s+who\s+(?:" + _OWNERSHIP_VERBS + r")\b"
    + r"|\bit\s+was\s+me\s+who\s+(?:" + _OWNERSHIP_VERBS + r")\b"
    + r"|\b(?:was|were|got|been|is)\s+(?:" + _OWNERSHIP_VERBS + r")\s+by\s+me\b"
    r"|\bi\s+was\s+(?:responsible\s+for|the\s+owner\s+of|the\s+lead\s+on|in\s+charge\s+of)\b"
    # Possessive claims, the most natural answer to the engine's own probe. None of nine
    # counted: "My part was the advisory-lock fix" scored ownership as nothing. Narrow on
    # purpose: "my job is at a bank" and "that was my manager's call" are not claims.
    r"|\bmy\s+(?:part|role|contribution|piece)\s+(?:was|is|were)\b"
    r"|\b(?:was|is)\s+my\s+(?:change|fix|responsibility|job|design|idea|decision|call)\b"
    r"|\b(?:was|is|were)\s+mine\b"
    r"|\bi\s+(?:take|takes|took|taken|have\s+taken)\s+(?:on|over|ownership\s+of|charge\s+of)\b",
    re.I,
)
#: A cost named alongside what was gained. The list did not contain the word "tradeoff",
#: so "the tradeoff was extra operational complexity" counted as nothing, and of ten
#: ordinary answers to the engine's own tradeoff probe three were recognised. Anchored,
#: so "I accepted the offer" and "we chose Postgres" stay what they are.
_TRADEOFF = re.compile(
    r"\b((give|gives|gave|given|giving) up|traded|trade[- ]?offs?|costs? us"
    r"|at the (expense|cost) of|downside|slower|doubles|doubled|sacrific\w+|in exchange"
    r"|compromise)\b"
    # "We trade latency for durability". Not "trades" on its own: in a payments interview
    # "we reconcile trades nightly" is an ordinary sentence.
    r"|\btrades?\s+\w+(\s+\w+)?\s+for\b"
    # "The cost was parallel reconciliation", "the catch was", "on the flip side". Not "the
    # cost of living" or "I accepted the cost": a cost has to be named as the price paid.
    r"|\bthe\s+(cost|catch|price)\s+(was|is)\b|\bon\s+the\s+flip\s+side\b"
    r"|\baccept(s|ed)?\s+(higher|more|less|lower|some|a bit of|extra|worse)\b"
    r"|\b(choose|chooses|chose|chosen)\s+\w+(\s+\w+)?\s+over\b",
    re.I,
)
#: Forming and testing a hypothesis. Four of ten ordinary debugging answers were
#: recognised: "I ruled out the network", "I isolated it to the worker" and "I added
#: logging and found..." counted for nothing. "profile" alone is not profiling, and
#: adding a feature is not adding instrumentation.
_HYPOTHESIS = re.compile(
    r"\b(hypothes\w+|suspect(s|ed)?|reproduc\w+|repro|bisect\w*|narrow(s|ed)"
    r"|rul(e|es|ed) out|isolat(e|es|ed)|profil(ed|ing|er)|flame ?graphs?|trac(e|es|ed))\b"
    r"|\b(my|our|first)\s+(guess|theory|suspicion)\b"
    r"|\b(add|adds|added)\s+(some\s+)?(logging|logs|tracing|metrics|instrumentation)\b"
    r"|\b(check|checks|checked|look|looks|looked)\s+(at\s+)?the\s+"
    r"(logs|metrics|timestamps|traces|dashboards?|heap)\b"
    # "I dug into the logs", "stepped through it in a debugger", "set a breakpoint". Tied to
    # what was examined, so "dug into the feature backlog" is not debugging.
    r"|\b(dug|dig|digs|digging)\s+into\s+the\s+(logs|metrics|traces|code|heap|dump|data)\b"
    r"|\b(stepped|step|steps|stepping)\s+through\s+(it|the\s+code|the\s+\w+\s+path)\b"
    r"|\b(debugger|breakpoints?)\b",
    re.I,
)
#: Content-free words. "you know" and "um" are deliberately absent: they are filler,
#: which is delivery, not substance. Confusing the two cost a candidate three points in
#: the matched-pair evals.
_VAGUE = re.compile(r"\b(basically|stuff|things|various|pretty much|a lot of)\b", re.I)
#: Verbal filler. Not vagueness, and not weakness. It correlates with nervousness and
#: with speaking a second language, so anything that reads it as a lack of substance is
#: scoring the candidate's delivery. Stripped before any judgement is made.
#: The comma before a filler word goes with it. Removing only "um," left "I, um,
#: reproduced it" as "I, reproduced it", and the stray comma between the pronoun and the
#: verb broke ownership: the same answer with filler scored ownership 3 against 4 without.
#: The matched-pair eval compared only the overall score and missed it.
_FILLER = re.compile(
    r",?\s*\b(u+m+|u+h+|e+r+m*|a+h+|you know|i mean|kind of|sort of)\b[,.]?\s*", re.I
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


#: A hyphen joining two words. Recognisers write the same compound three ways: "trade
#: off", "tradeoff", "trade-off". Eight of sixteen such spellings lost their evidence,
#: "I rolled-out the fix" and "the root-cause was" among them, so which spelling a
#: recogniser picked decided the score.
_JOINED = re.compile(r"(?<=[A-Za-z])-(?=[A-Za-z])")
#: "re wrote", split where the recogniser heard a pause in the prefix.
_RE_SPLIT = re.compile(
    r"\bre\s+(?=(?:write|writes|wrote|written|build|builds|built|design|designs|designed)\b)",
    re.I,
)


#: A lone "1" with nothing measured by it. "One merchant" is deliberately not a figure, and
#: the digit for it was, so the same answer scored 3 or 4 depending on how the recogniser
#: chose to write the word. Rewritten to the word rather than removed, so it still reads.
_BARE_ONE = re.compile(
    r"(?<![\d.,])1(?![\d.,])"
    r"(?!\s*(?:%|(?:ms|s|x|k|m|gb|mb|qps|rps|percent|millisecond|second|minute|hour|day"
    r"|week|month|year)s?\b))",
    re.I,
)


def normalise(text: str) -> str:
    """What the candidate said, with delivery and transcription artefacts removed.

    Filler and repairs are how people talk, not how well they did the work, and how a
    recogniser spelled a compound word is neither. Everything that judges content runs on
    this; everything quoted back keeps their own words.
    """
    out = _BARE_ONE.sub(" one ", strip_repairs(strip_filler(text)))
    out = _JOINED.sub(" ", out)
    return _RE_SPLIT.sub("re", out)


_SIGNALS: Dict[str, Sequence] = {
    "technical_depth": (_CAUSAL, _NUMBER),
    "ownership": (_FIRST_PERSON,),
    "tradeoffs": (_TRADEOFF,),
    "debugging": (_HYPOTHESIS,),
    "communication": (_CAUSAL, _STRUCTURE),
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
    # Only dimensions the role counts. One weighted zero adds nothing to the overall, so it
    # cannot be what makes the overall trustworthy; and when every dimension with evidence
    # was weighted zero, the report crashed dividing by zero after the call had finished.
    scored = [
        s for s in scores if not s.insufficient and role.weights.get(s.dimension, 1.0) > 0
    ]

    if len(scored) < MIN_SCORED_DIMENSIONS:
        return Assessment(
            overall=None,
            band="insufficient signal",
            dimensions=scores,
            flags=list(flags or ()) + [
                "Only %d of %d dimensions had citable evidence. Offer a human screen."
                % (len(scored), sum(1 for d in DIMENSIONS if role.weights.get(d, 1.0) > 0))
            ],
            duration_s=duration,
            judge=judge.name,
        )

    total_w = sum(role.weights.get(s.dimension, 1.0) for s in scored)
    weighted = sum(s.score * role.weights.get(s.dimension, 1.0) for s in scored)
    mean = weighted / total_w  # 1..4

    # 1..4 onto 1..10. The scale is presentation; the judgement is the rubric.
    # Halves round up. round() rounds them to even, so exactly-halfway profiles went both
    # ways: 3,3,2,2 showed 6 from 5.5 while 4,4,3,3 showed 8 from 8.5. The epsilon keeps a
    # half that float arithmetic lands a hair under from rounding down.
    raw = (mean - MIN_SCORE) / (MAX_SCORE - MIN_SCORE) * 9 + 1
    overall = int(math.floor(raw + 0.5 + 1e-9))

    return Assessment(
        overall=overall,
        # Gaps only in dimensions the role counts. A role that weights communication zero
        # held a candidate at 10/10 on everything it does count to "with reservations",
        # because they had not spoken to communication.
        band=band_for(
            overall, [s for s in scores if role.weights.get(s.dimension, 1.0) > 0]
        ),
        dimensions=scores,
        flags=list(flags or ()),
        duration_s=duration,
        judge=judge.name,
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
{{"score": 1-4 or null, "quote": "the candidate's own words, verbatim, or null",
  "reason": "one sentence"}}

The quote must be copied exactly from one of the Candidate lines below, without the
"Candidate:" label. Quote one continuous passage: do not join or shorten passages with
"...", because an elided quote is not checked as evidence.
The interviewer's words are never evidence about the candidate, even where a question
repeats what the candidate said. A quote you cannot find in the
candidate's lines is a fabrication and the answer is null instead.

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
        #: Dimensions scored with no quote at all. Not usable, and not a fabrication.
        self.uncited: List[str] = []

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

        if not quote:
            # A score with nothing cited. Evidence or it did not happen, so it is not
            # used. But nothing was made up either, and this used to be counted and
            # described as a fabrication: "cited a quote not present", when nothing had
            # been cited at all.
            self.uncited.append(dimension)
            return DimensionScore(
                dimension,
                None,
                [],
                "Scored %s but cited nothing, so the score is not used." % score,
            )
        if not _appears_in(quote, units):
            # The score might be right. A citation that cannot be located in what the
            # candidate said is the one thing a report must never carry, so the score
            # goes with it. "Not present in the transcript" was wrong for a quote taken
            # from the interviewer's question, which is in the transcript.
            self.fabrications.append(dimension)
            return DimensionScore(
                dimension,
                None,
                [],
                "Scored %s but cited a quote not found in the candidate's answers." % score,
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


def _whole_score(value) -> Optional[int]:
    """A rubric score, only if the model actually gave a whole number.

    It went through `int()`, which turns `true` into 1, a real score at the bottom of the
    rubric, and truncates 3.9 to 3 and 2.5 to 2. Each of those is a number the model did
    not give. A whole number is accepted however it is written: 3, 3.0, "3".
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str) and re.fullmatch(r"\s*[0-9]+\s*", value):
        return int(value)
    return None


def parse_verdict(raw: str):
    """Pull (score, quote, reason) out of a model's reply, or None if unreadable.

    Tolerant of a model wrapping JSON in prose or a code fence, which they do. Not
    tolerant of anything it cannot parse: a guess here becomes a number in a hiring
    report.
    """
    import json

    if not isinstance(raw, str):
        return None
    # Every complete JSON object in the reply, not the span from the first brace to the
    # last. That span swallowed any other brace in the reply, so a verdict followed by a
    # note mentioning "{placeholder}" was thrown away as unreadable.
    decoder = json.JSONDecoder()
    verdicts = []
    at = raw.find("{")
    while at != -1:
        try:
            obj, end = decoder.raw_decode(raw, at)
        except ValueError:
            at = raw.find("{", at + 1)
            continue
        if isinstance(obj, dict) and "score" in obj:
            verdicts.append(obj)
        at = raw.find("{", end)
    if not verdicts:
        return None
    # Two different verdicts is not a verdict. Picking the first or the last would be
    # guessing which one the model meant, and a guess here becomes a number in a report.
    if len({json.dumps(v, sort_keys=True) for v in verdicts}) > 1:
        return None
    data = verdicts[0]

    score = data.get("score")
    if score is not None:
        score = _whole_score(score)
        if score is None:
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
    spaced = _NUMBER_UNIT.sub(" ", _QUOTE_FILLER.sub(" ", fold(text)))
    words = _QUOTE_PUNCT.sub(" ", spaced).lower().split()
    return " %s " % " ".join(words) if words else ""


#: Sounds, not words, dropped on both sides of a quote comparison. A judge tidying "I, uh,
#: wrote the retry budget myself" into "I wrote the retry budget myself" was voided as a
#: fabrication. Narrower than the content filter on purpose: "I kind of led it" quoted as
#: "I led it" overstates what was said, so hedges must still match.
_QUOTE_FILLER = re.compile(r"\b(u+m+|u+h+|e+r+m*|a+h+|you know)\b", re.I)

#: Between a number and the unit written against it. "30ms" and "30 ms" are the same thing,
#: and a recogniser writes one where a judge writes the other, which voided the score. Only
#: digit then letter, so "p99" stays one token.
_NUMBER_UNIT = re.compile(r"(?<=\d)(?=[^\W\d_])")


def _appears_in(quote: str, units: Sequence[QAUnit]) -> bool:
    """Whitespace and case are not fabrication; missing words are.

    Only the candidate's answers count. The interviewer's questions used to count too,
    so a judge citing "you personally do" from "What did you personally do?" scored the
    candidate 4 on ownership with the interviewer's own words as the evidence.
    """
    needle = _normalise(_unlabelled(quote))
    if not needle:
        return False
    return any(needle in _normalise(u.answer) for u in units)


#: The label the judge sees in front of every candidate line. Copying it into a quote is
#: formatting, not fabrication, and it voided genuine quotes. Only this label: a quote
#: labelled as the interviewer's is still not evidence about the candidate.
_CANDIDATE_LABEL = re.compile(r"^\s*[\"'“‘]?\s*candidate\s*:\s*", re.I)


def _unlabelled(quote: str) -> str:
    return _CANDIDATE_LABEL.sub("", quote, count=1)


def _timestamp_of(quote: str, units: Sequence[QAUnit]) -> float:
    needle = _normalise(_unlabelled(quote))
    for u in units:
        if needle in _normalise(u.answer):
            return u.answered_at_s
    return 0.0
