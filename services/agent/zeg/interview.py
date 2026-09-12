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
from .config import CallConfig
from .engine import InterviewEngine
from .prompts import CONSENT_DECLINED, GREETING, WRAP_UP

#: How often the model is re-grounded. Its audio context is roughly two minutes, so a
#: briefing older than this is worth resending even if nothing changed.
BRIEFING_INTERVAL_S = 60.0

#: Consent detection. Crude and deliberately conservative: anything that is not a clear
#: yes is treated as not-yet-consented, and silence never counts as agreement.
_YES = re.compile(r"\b(yes|yeah|yep|sure|that'?s fine|ok|okay|of course|go ahead|fine)\b", re.I)
_NO = re.compile(r"\b(no|nope|not really|i'?d rather not|don'?t|do not|rather you didn'?t|refuse)\b", re.I)


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


class Interview:
    """Drive one call. Feed it backend events, perform the actions it returns."""

    def __init__(
        self,
        engine: Optional[InterviewEngine] = None,
        call: Optional[CallConfig] = None,
        greeting: str = GREETING,
    ) -> None:
        self.call = call or CallConfig()
        self.engine = engine or InterviewEngine(call=self.call)
        self.greeting = greeting
        self.record = InterviewRecord()
        self._last_brief_s = -BRIEFING_INTERVAL_S
        self._wrapped = False
        self._asked_consent = False

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
            # The candidate started talking. Nothing to decide; the backend already
            # stopped. Recorded so the report can show they were cut off.
            return []

        if isinstance(event, AgentText) and event.final:
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
            return self._resolve_consent(text, t_s)

        self.engine.note_caller(text, t_s)

        actions: List[Action] = []
        phase = self.engine.advance(t_s)

        # Re-ground the model when the topic moves or the briefing goes stale. Turn
        # boundaries are the only safe moment: mid-response the model is mid-sentence.
        if phase is not None or t_s - self._last_brief_s >= BRIEFING_INTERVAL_S:
            actions.append(Brief(self.engine.briefing(t_s)))
            self._last_brief_s = t_s

        if self.engine.should_wrap_up(t_s) and not self._wrapped:
            self._wrapped = True
            actions.extend(self._say(WRAP_UP, t_s))
            return actions

        probe = self.engine.next_probe()
        if probe is not None:
            actions.append(Probe("Ask for %s." % probe))
        return actions

    def _resolve_consent(self, text: str, t_s: float) -> List[Action]:
        """No recording, no interview. Silence is not agreement."""
        if _NO.search(text) or not _YES.search(text):
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

    def _end(self, reason: str) -> List[Action]:
        self.record.ended = reason
        return [EndCall(reason)]

    # --- afterwards -----------------------------------------------------------

    def transcript_for_scoring(self) -> Sequence[Turn]:
        return list(self.record.transcript)
