"""The interview engine.

A state machine, not a prompt. It owns the plan, the wall clock, what has been covered
and what the candidate claimed. The model's job is to phrase the next question and to
judge an answer; deciding *what* to ask, *when* to move on and *when* to stop is program
control.

Two reasons this separation exists. A model left to steer a 15-minute interview drifts,
repeats itself, runs long and occasionally asks something a lawyer will not enjoy
reading. And the model reliably holds about two minutes of audio context while an
interview runs fifteen, so it cannot be the thing that remembers. This class is the
memory; `briefing()` is what gets handed back to the model at a turn boundary.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .blocklist import assert_allowed
from .config import CallConfig
from .memory import shorten

# --- The plan ----------------------------------------------------------------

#: Rubric dimensions. Communication is scored on structure and responsiveness only.
#: Accent, fluency, pace and vocabulary breadth are excluded by construction; see
#: docs/04-interview-design.md.
DIMENSIONS = (
    "technical_depth",
    "ownership",
    "tradeoffs",
    "debugging",
    "communication",
)


@dataclass(frozen=True)
class Phase:
    name: str
    until_s: float
    goal: str
    dimensions: Sequence[str] = ()


#: Wall-clock boundaries, not step counts. The clock moves whether or not the
#: conversation is going well, which is what keeps calls comparable across candidates.
DEFAULT_PLAN: Sequence[Phase] = (
    Phase("greeting", 60, "Disclose AI, get recording consent, set expectations."),
    Phase("warmup", 180, "One recent project in their own words.",
          ("communication",)),
    Phase("depth_one", 420, "Drill into a claim from the warm-up, three or four levels.",
          ("technical_depth", "ownership")),
    Phase("depth_two", 660, "A second dimension, role-specific.",
          ("technical_depth", "tradeoffs")),
    Phase("scenario", 810, "A short design or debugging situation under ambiguity.",
          ("debugging", "tradeoffs")),
    Phase("close", 900, "Their questions, next steps, thank you."),
)

#: The probe ladder. Stop descending when an answer becomes specific and costly to
#: fabricate, or when two consecutive levels return generality.
PROBE_LADDER = (
    "what they personally did, as opposed to the team",
    "a number: throughput, latency, data volume, instance count",
    "a tradeoff they accepted, because real work costs something",
    "what broke afterwards that they did not expect",
)

#: How each rung's answer is labelled in a briefing, in ladder order.
RUNG_LABELS = ("their own part", "the figure", "the tradeoff", "what broke afterwards")
assert len(RUNG_LABELS) == len(PROBE_LADDER)

#: Lines a briefing spends on claims and the answers under the live one. Without answers
#: that is the same four claims as before; a fully answered ladder leaves room for one
#: older claim beside it.
CLAIM_LINES = 6

#: Phrases that indicate an answer stayed general. Crude on purpose: the engine only
#: needs to know whether to descend further, and the scoring pass judges properly.
#: Content-free words. Filler ("um", "you know") is excluded on purpose: it is
#: delivery, not substance, and treating it as vagueness penalises nervous and
#: second-language speakers for saying exactly the same thing.
_VAGUE = re.compile(
    r"\b(we just|basically|stuff|things|various|some kind of|pretty much|"
    r"a lot of|generally|typically|it depends)\b",
    re.I,
)
_CAUSAL_OR_OUTCOME = re.compile(
    r"\b(because|so that|which meant|turned out|root cause)\b", re.I
)


# --- State -------------------------------------------------------------------


@dataclass
class Claim:
    """Something the candidate asserted that is worth probing."""

    text: str
    at_s: float
    probed_to: int = 0  # how far down PROBE_LADDER we have gone
    #: (rung index, what the candidate said) for each probe answered with substance.
    answers: List[Tuple[int, str]] = field(default_factory=list)


@dataclass
class Evidence:
    dimension: str
    quote: str
    at_s: float


@dataclass
class InterviewState:
    phase: str = "greeting"
    consent: Optional[bool] = None
    claims: List[Claim] = field(default_factory=list)
    evidence: List[Evidence] = field(default_factory=list)
    asked: List[str] = field(default_factory=list)
    vague_streak: int = 0
    #: Subjects the agent has already had to be pulled off. Kept because a briefing is
    #: what a fresh session is primed with, and a rollover would otherwise hand the next
    #: session only the system prompt the model has already ignored once.
    prohibited_subjects: List[str] = field(default_factory=list)
    #: True between issuing a probe and hearing the answer to it. Without this, every
    #: specific answer looked like a brand new claim and the ladder reset instead of
    #: descending, so a probe never got past its first rung.
    probe_outstanding: bool = False


class InterviewEngine:
    """Owns one interview. Drive it by reporting what was said and asking what next."""

    def __init__(
        self,
        call: Optional[CallConfig] = None,
        plan: Sequence[Phase] = DEFAULT_PLAN,
    ) -> None:
        self.call = call or CallConfig()
        self.plan = tuple(plan)
        self.state = InterviewState()

    # --- clock ---------------------------------------------------------------

    def phase_at(self, t_s: float) -> Phase:
        for p in self.plan:
            if t_s < p.until_s:
                return p
        return self.plan[-1]

    def should_wrap_up(self, t_s: float) -> bool:
        """True once the wall clock says start closing, whatever the model is doing."""
        return t_s >= self.call.wrap_up_at_s

    def is_over(self, t_s: float) -> bool:
        return t_s >= self.call.max_duration_s

    def advance(self, t_s: float) -> Optional[str]:
        """Move to the phase the clock says we are in. Returns the new phase, or None."""
        p = self.phase_at(t_s)
        if p.name != self.state.phase:
            self.state.phase = p.name
            return p.name
        return None

    # --- recording what happened ---------------------------------------------

    def note_consent(self, granted: bool) -> None:
        self.state.consent = granted

    def note_agent(self, text: str, t_s: float) -> None:
        """Record a question the agent asked. Text is gated before it reaches here."""
        self.state.asked.append(text)

    def note_caller(self, text: str, t_s: float) -> None:
        """Record an answer and judge, crudely, whether it was specific.

        An answer to an outstanding probe deepens the claim being probed; it does not
        start a new one. Treating it as new was the bug that kept the ladder pinned to
        its first rung through an entire interview.
        """
        from .scoring import has_number, normalise, signals  # local: scoring imports engine

        spoken = normalise(text)
        specific = bool(_CAUSAL_OR_OUTCOME.search(spoken)) or has_number(spoken)
        vague = bool(_VAGUE.search(spoken)) and not specific
        self.state.vague_streak = self.state.vague_streak + 1 if vague else 0

        # Nothing ever recorded evidence during a call, so every briefing said all five
        # dimensions were still uncovered, and a model told "no evidence for ownership"
        # straight after "I wrote the fix myself" asks for it again. The same surface
        # markers the heuristic judge scores on. Scoring still reads the transcript.
        covered = {e.dimension for e in self.state.evidence}
        for dimension in signals(text):
            if dimension not in covered:
                self.record_evidence(dimension, text, t_s)

        if self.state.probe_outstanding:
            self.state.probe_outstanding = False
            # Kept with the claim, because this is what the probe was for. It used to be
            # dropped, so after a rollover the briefing named the project and none of
            # what the candidate had said about it, and the fresh session asked again.
            claim = self.state.claims[-1] if self.state.claims else None
            if claim is not None and not vague and claim.probed_to > 0:
                claim.answers.append((claim.probed_to - 1, text))
            return
        if not vague and len(text.split()) >= 4:
            self.state.claims.append(Claim(text=text, at_s=t_s))

    def note_prohibited(self, category: str) -> None:
        """The agent had to be pulled off this subject. Recorded once, kept for good."""
        if category not in self.state.prohibited_subjects:
            self.state.prohibited_subjects.append(category)

    def record_evidence(self, dimension: str, quote: str, t_s: float) -> None:
        if dimension not in DIMENSIONS:
            raise ValueError("unknown rubric dimension: %r" % dimension)
        self.state.evidence.append(Evidence(dimension, quote, t_s))

    # --- deciding what happens next ------------------------------------------

    def uncovered(self) -> List[str]:
        """Dimensions with no evidence yet, in rubric order."""
        seen = {e.dimension for e in self.state.evidence}
        return [d for d in DIMENSIONS if d not in seen]

    def next_probe(self) -> Optional[str]:
        """The next rung of the ladder for the live claim, or None to move on.

        Descending stops when two consecutive answers stayed general. That is itself
        a signal, and it is recorded rather than treated as a failed probe.
        """
        if self.ladder_stalled:
            return None
        if not self.state.claims:
            return None
        claim = self.state.claims[-1]
        if claim.probed_to >= len(PROBE_LADDER):
            return None
        rung = PROBE_LADDER[claim.probed_to]
        claim.probed_to += 1
        self.state.probe_outstanding = True
        return rung

    @property
    def ladder_stalled(self) -> bool:
        """Two general answers in a row. The engine stops descending and moves on.

        One rule, shared by everything that needs to know, so the question logic and
        the rollover guard cannot disagree about whether a ladder is still live.
        """
        return self.state.vague_streak >= 2

    @property
    def probe_in_progress(self) -> bool:
        """True while a claim is partway down the ladder.

        Used to hold off a session rollover: the descent is exactly the thread a fresh
        session would lose.
        """
        if not self.state.claims:
            return False
        if self.ladder_stalled:
            # An abandoned ladder is finished. Counting it as in progress switched off
            # rollover for the rest of the call once a candidate went vague part way
            # down, because vague answers never start a new claim to replace it.
            return False
        # The final rung counts until the candidate has answered it. Checking the rung
        # count alone declared the ladder finished the moment its last question was
        # issued, so the rollover policy, which waits for a finished ladder, rolled the
        # session on that very turn. The question was steered into a model that closed
        # a moment later and was never asked.
        return (0 < self.state.claims[-1].probed_to < len(PROBE_LADDER)
                or self.state.probe_outstanding)

    def speak(self, text: str) -> str:
        """Gate an outbound utterance. Raises ProhibitedQuestion if it must not be said.

        Everything the agent says goes through here. It is the last thing between the
        model and the candidate's ear.
        """
        return assert_allowed(text)

    # --- memory ---------------------------------------------------------------

    def briefing(self, t_s: float, max_claims: int = 4) -> str:
        """A compact restatement of the interview so far.

        Handed back to the model at a turn boundary, because the model holds roughly
        two minutes of context and this call runs fifteen. It is deliberately short:
        the point is to re-ground, not to replay the transcript. The full record lives
        on our side and the scoring pass reads that, not this.
        """
        p = self.phase_at(t_s)
        mins, secs = divmod(int(t_s), 60)
        lines = [
            "Elapsed %d:%02d of %d minutes. Phase: %s."
            % (mins, secs, self.call.max_duration_s // 60, p.name),
            "Goal right now: %s" % p.goal,
        ]
        if self.state.claims:
            lines.append("The candidate has claimed:")
            lines.extend(self._claim_lines(max_claims))
        if self.state.prohibited_subjects:
            # Carried in every briefing, so it survives a rollover: the fresh session
            # would otherwise start from the same system prompt the model already
            # ignored once.
            lines.append(
                "Never ask about: %s."
                % ", ".join(s.replace("_", " ") for s in self.state.prohibited_subjects)
            )
        missing = self.uncovered()
        if missing:
            lines.append("Still no evidence for: %s." % ", ".join(missing))
        if self.ladder_stalled:
            lines.append("Two answers in a row stayed general. Change topic.")
        if self.should_wrap_up(t_s):
            lines.append("Time is nearly up. Close the interview.")
        return "\n".join(lines)

    def _claim_lines(self, max_claims: int) -> List[str]:
        """The live claim with what the candidate said under each probe, and as many
        older claims as fit beside it. Shortened from the middle, because a claim or an
        answer usually ends on its figure."""
        live, older = self.state.claims[-1], self.state.claims[-max_claims:-1]
        live_lines = ["  - %s" % shorten(live.text, 90)] + [
            "      %s: %s" % (RUNG_LABELS[rung], shorten(text, 90))
            for rung, text in live.answers
        ]
        room = max(0, CLAIM_LINES - len(live_lines))
        older = older[len(older) - room:] if room else []
        return ["  - %s" % shorten(c.text, 90) for c in older] + live_lines
