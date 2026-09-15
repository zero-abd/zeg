"""One interview, driven.

The engine knows the plan, the backend carries the audio, the block list gates what may
be said and the scoring pass reads the record afterwards. This is the thing that holds
them together: events from the model go in, actions come out.

It is deliberately a pure state machine over events with no I/O of its own. The caller
performs the actions. That keeps the compliance-critical parts — consent, the wall
clock, the block list — testable without a model, a socket, or a microphone, which is
the only way they will actually stay tested.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from .backends.base import AgentInterrupted, AgentText, UserTranscript
from .blocklist import ProhibitedQuestion
from .textnorm import fold
from .config import CallConfig
from .engine import InterviewEngine
from .memory import RolloverPolicy, SessionSeed, last_exchange
from .prompts import CONSENT_DECLINED, GREETING, SYSTEM_PROMPT, WRAP_UP

#: How often the model is re-grounded. Its audio context is roughly two minutes, so a
#: briefing older than this is worth resending even if nothing changed.
BRIEFING_INTERVAL_S = 60.0

#: Consent detection. The two failure directions are not equally bad, so the rules are
#: not symmetrical. See `reads_as_consent`.

#: Agreement that happens to contain a refusal word. English does this constantly: "no
#: problem" and "I don't mind" are agreements, and reading them literally ends the
#: interview for someone who just said yes.
_AGREEMENT_IDIOM = re.compile(
    r"\bno (problem|worries|issue|objection)\b|\b(i )?do(n'?t| not) mind\b", re.I
)

_YES = re.compile(
    r"\b(yes|yeah|yep|yup|sure|absolutely|of course|go ahead|okay|ok)\b"
    r"|\bthat'?s fine\b|\bthat is fine\b|\bfine (by|with) me\b|\bthat works\b",
    re.I,
)

_NO = re.compile(
    r"\b(no|nope|nah|refuse)\b|\bnot really\b"
    r"|\bi'?d rather not\b|\bi would rather not\b"
    r"|\brather you did ?n'?t\b|\brather you would not\b"
    r"|\bplease do(n'?t| not)\b|\bdo(n'?t| not) record\b",
    re.I,
)

#: Hedged, questioning or reluctant. Not a refusal, and emphatically not a yes. These
#: are the dangerous ones: several contain an agreement word while meaning "maybe".
_UNSURE = re.compile(
    r"\bnot sure\b|\bmaybe\b|\bi guess\b|\bi suppose\b|\bif i have to\b"
    r"|\bwhat happens\b|\brepeat that\b|\bdoes it have to\b"
    r"|\bwhat was the question\b|\bhave to be\b",
    re.I,
)


def reads_as_consent(text: str) -> bool:
    """True only for a clear yes.

    The two failure directions are not equally bad. A false yes records someone who
    declined, which is the one thing this project promised not to do. A false no ends
    an interview for someone who agreed, which is rude, costs a candidate, and is
    recoverable by a human. So this requires a clear yes and treats everything else,
    silence included, as refusal.

    Order matters. Hedging is checked first, because "I'm not sure, yes maybe" contains
    a yes and is not one. Then agreement idioms are rewritten, because "no problem" is
    not a no. Only then is a literal refusal looked for.
    """
    # A typographic apostrophe in "didn't" slipped past every refusal pattern while
    # "yes" still matched, so a refusal was recorded as consent. Fold first.
    text = fold(text)
    if _UNSURE.search(text):
        return False
    plain = _AGREEMENT_IDIOM.sub(" yes ", text)
    if _NO.search(plain):
        return False
    return bool(_YES.search(plain))


# --- Actions the caller performs ---------------------------------------------


@dataclass
class Speak:
    """Say this. Already gated; safe to synthesise."""

    text: str


@dataclass
class Brief:
    """Re-ground the model at a turn boundary. Not spoken."""

    text: str


@dataclass
class Probe:
    """What to ask next. A steer, not a script.

    Distinct from Brief because the two are consumed differently: a briefing re-grounds
    the model in what it has forgotten, a probe directs the next question. Collapsing
    them into one type left the caller unable to tell "here is context" from "ask this".
    """

    instruction: str


@dataclass
class Rollover:
    """Open a fresh model session primed with this, and swap at this turn boundary.

    The model's context horizon is shorter than the interview, so the session is
    replaced rather than allowed to drift past what it can hold. The candidate hears a
    beat of silence; they do not hear the agent forget them.
    """

    seed: SessionSeed

    @property
    def text(self) -> str:
        return self.seed.render()


@dataclass
class EndCall:
    reason: str


Action = object  # one of the above


@dataclass
class Turn:
    at_s: float
    speaker: str  # "agent" | "caller"
    text: str


@dataclass
class InterviewRecord:
    transcript: List[Turn] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)
    consent: Optional[bool] = None
    ended: Optional[str] = None
    rollovers: int = 0


class Interview:
    """Drive one call. Feed it backend events, perform the actions it returns."""

    def __init__(
        self,
        engine: Optional[InterviewEngine] = None,
        call: Optional[CallConfig] = None,
        greeting: str = GREETING,
        rollover: Optional[RolloverPolicy] = None,
        system_prompt: str = SYSTEM_PROMPT,
    ) -> None:
        self.call = call or CallConfig()
        self.engine = engine or InterviewEngine(call=self.call)
        self.greeting = greeting
        self.rollover = rollover or RolloverPolicy()
        self.system_prompt = system_prompt
        self.record = InterviewRecord()
        self._last_brief_s = -BRIEFING_INTERVAL_S
        self._wrapped = False
        self._asked_consent = False
        self._session_started_s = 0.0
        #: The candidate talked over the disclosure before consent was settled.
        self._disclosure_interrupted = False

    # --- lifecycle ------------------------------------------------------------

    def start(self) -> List[Action]:
        """The opening. Disclosure and the consent request, both mandatory and both
        literals rather than anything the model chose."""
        self._asked_consent = True
        return self._say(self.greeting, 0.0)

    def on_event(self, event, t_s: float) -> List[Action]:
        """Translate one backend event into what should happen next."""
        if self.record.ended:
            return []

        actions: List[Action] = []

        # The clock outranks the conversation. Checked before anything else so a
        # runaway model cannot talk past the limit.
        if self.engine.is_over(t_s):
            return self._end("time limit reached")

        if isinstance(event, AgentInterrupted):
            # The candidate started talking and the backend already stopped. Before
            # consent is settled the only thing the agent has said is the disclosure, so
            # an interruption here means they may not have heard that the call is
            # recorded.
            if self.record.consent is None and self._asked_consent:
                self._disclosure_interrupted = True
            return []

        if isinstance(event, AgentText) and event.final:
            # A backend echoes back what it spoke, including the fixed utterances we
            # handed it with say(). Recording both put the greeting in the transcript
            # twice. The echo is a confirmation, not a second turn.
            if not self._already_recorded(event.text):
                self.record.transcript.append(Turn(t_s, "agent", event.text))
                self.engine.note_agent(event.text, t_s)
            return []

        if isinstance(event, UserTranscript) and event.final:
            return self._on_answer(event.text, t_s)

        return actions

    # --- the candidate said something ----------------------------------------

    def _on_answer(self, text: str, t_s: float) -> List[Action]:
        self.record.transcript.append(Turn(t_s, "caller", text))

        if self.record.consent is None and self._asked_consent:
            if self._disclosure_interrupted:
                # Whatever they said over the disclosure is not an answer to a question
                # they may not have heard in full. Taking it as one recorded consent to a
                # recording the candidate had cut off before it was announced.
                self._disclosure_interrupted = False
                self.record.flags.append(
                    "The candidate talked over the recording disclosure. It was repeated "
                    "in full before consent was taken."
                )
                return self._say(self.greeting, t_s)
            return self._resolve_consent(text, t_s)

        self.engine.note_caller(text, t_s)

        actions: List[Action] = []
        phase = self.engine.advance(t_s)

        # Re-ground the model when the topic moves or the briefing goes stale. Turn
        # boundaries are the only safe moment: mid-response the model is mid-sentence.
        if phase is not None or t_s - self._last_brief_s >= BRIEFING_INTERVAL_S:
            actions.append(Brief(self.engine.briefing(t_s)))
            self._last_brief_s = t_s

        if self.engine.should_wrap_up(t_s):
            if not self._wrapped:
                self._wrapped = True
                actions.extend(self._say(WRAP_UP, t_s))
            # Past the wrap-up the interview is closing: the candidate's questions, next
            # steps, thanks. Only the answer that triggered the wrap-up used to stop here.
            # Every later answer fell through and issued a fresh probe, so the agent said
            # it was out of time and then asked what broke afterwards, even in reply to
            # the candidate asking a question of their own. It could also roll the
            # session and pay for a pause in the last minute and a half.
            return actions

        probe = self.engine.next_probe()
        if probe is not None:
            actions.append(Probe("Ask for %s." % probe))

        # Turn boundaries are the only safe moment to replace a session, and a probe
        # still descending is a thread a fresh session would drop.
        if self.rollover.should_roll(
            session_age_s=t_s - self._session_started_s,
            at_turn_boundary=True,
            probe_in_progress=self.engine.probe_in_progress,
            frames_used=self.rollover.frames_for(t_s - self._session_started_s),
        ):
            actions.append(Rollover(self._seed(t_s)))
            self.record.rollovers += 1
            self._session_started_s = t_s
            self._last_brief_s = t_s  # the seed already carries the briefing
        return actions

    def _resolve_consent(self, text: str, t_s: float) -> List[Action]:
        """No recording, no interview. Silence is not agreement."""
        if not reads_as_consent(text):
            self.record.consent = False
            self.engine.note_consent(False)
            actions = self._say(CONSENT_DECLINED, t_s)
            actions.extend(self._end("consent declined"))
            return actions
        self.record.consent = True
        self.engine.note_consent(True)
        self._last_brief_s = t_s
        return [Brief(self.engine.briefing(t_s))]

    # --- helpers --------------------------------------------------------------

    def _say(self, text: str, t_s: float) -> List[Action]:
        """Gate an utterance. A blocked one is dropped and flagged, never spoken.

        Dropping rather than rephrasing is deliberate. A rephrase asks the thing that
        produced a prohibited question to try again, which is the wrong component to
        trust with the second attempt.
        """
        try:
            safe = self.engine.speak(text)
        except ProhibitedQuestion as e:
            self.record.flags.append("Blocked a prohibited question: %s" % e.violation)
            return []
        self.record.transcript.append(Turn(t_s, "agent", safe))
        self.engine.note_agent(safe, t_s)
        return [Speak(safe)]

    def _already_recorded(self, text: str) -> bool:
        for turn in reversed(self.record.transcript):
            if turn.speaker == "agent":
                return turn.text == text
            return False
        return False

    def _seed(self, t_s: float) -> SessionSeed:
        return SessionSeed(
            system_prompt=self.system_prompt,
            briefing=self.engine.briefing(t_s),
            last_exchange=last_exchange(self.record.transcript),
        )

    def _end(self, reason: str) -> List[Action]:
        self.record.ended = reason
        return [EndCall(reason)]

    # --- afterwards -----------------------------------------------------------

    def transcript_for_scoring(self) -> Sequence[Turn]:
        return list(self.record.transcript)
