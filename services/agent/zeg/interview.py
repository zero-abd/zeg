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

from .backends.base import AgentAudio, AgentInterrupted, AgentText, UserTranscript
from .blocklist import ProhibitedQuestion, check
from .hesitation import is_hesitation
from .textnorm import fold
from .config import CallConfig
from .engine import InterviewEngine
from .memory import RolloverPolicy, SessionSeed, last_exchange
from .prompts import (
    CONSENT_DECLINED,
    CONSENT_UNANSWERED,
    GREETING,
    PROHIBITED_REDIRECT,
    SYSTEM_PROMPT,
    WRAP_UP,
)

#: How often the model is re-grounded. Its audio context is roughly two minutes, so a
#: briefing older than this is worth resending even if nothing changed.
BRIEFING_INTERVAL_S = 60.0

#: How long both sides must have been quiet before the clock delivers the wrap-up on its
#: own. Long enough that it never cuts across the agent's sentence or the candidate's
#: pause; the model's audio arrives every 80 ms while it speaks.
QUIET_BEFORE_WRAP_UP_S = 2.0

#: How long the consent question waits in silence before the call ends. Counted from the
#: last thing either side said, so it starts once the disclosure has finished playing, and
#: a hesitation restarts it.
CONSENT_ANSWER_TIMEOUT_S = 15.0

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
    r"|\bthat'?s fine\b|\bthat is fine\b|\bfine (by|with) me\b|\bthat works\b"
    # Plain agreement that named none of the words above, and was refused. "Alright",
    # "Sounds good", "I agree" and "I consent" each ended the interview for someone who
    # had said yes. Every one has its negation in _NO, which is checked first.
    r"|\b(alright|all right|fine|certainly|definitely|agreed)\b"
    r"|\bsounds? good\b|\bi (fully |completely |totally )?(agree|consent)\b"
    r"|\bplease do\b|\bgo for it\b|\bworks for me\b|\bhappy with that\b",
    re.I,
)

_NO = re.compile(
    r"\b(no|nope|nah|refuse)\b|\bnot really\b"
    r"|\bi'?d rather not\b|\bi would rather not\b"
    r"|\brather you did ?n'?t\b|\brather you would not\b"
    r"|\bplease do(n'?t| not)\b|\bdo(n'?t| not) record\b"
    # A negated agreement is a refusal. "Absolutely not" and "I'm not okay with that"
    # each contain a word from the agreement list, and both were read as consent.
    r"|\b(absolutely|of course|sure|certainly|definitely) not\b"
    r"|\bnot (okay|ok|fine|comfortable|happy|alright|all right)\b"
    # The negations of the plainer agreements, so widening the list cannot turn
    # "I don't agree" or "That doesn't sound good" into consent.
    r"|\b(do|does|did|ca|can|could|would|wo|will)(n'?t| not) (really )?"
    r"(agree|consent|sound good|work for me)\b"
    r"|\bcannot (agree|consent)\b|\bnever (agree|consent)|\bdisagree\b",
    re.I,
)

#: A condition attached to the recording. "Of course, but can we skip the recording?"
#: agrees to the call and refuses the recording, which is the one thing the question
#: asked about. Only applies when recording is mentioned, so "yes, but please be quick"
#: still counts as a yes: a false no costs the candidate their interview.
_CONTRAST = re.compile(
    r"\b(but|though|although|however|unless|as long as|only if|provided)\b", re.I
)
_RECORDING = re.compile(r"\brecord(ed|ing|s)?\b", re.I)

#: A word against the recording. "Sure, skip the recording" agrees to the call and
#: refuses the recording with no contrast word, and was read as consent. This is a word
#: list, so it only catches opposition phrased with these words. A condition that never
#: mentions recording, like "as long as nothing is saved", is still missed.
_OPPOSED = re.compile(
    r"\b(skip|stop|pause|off|without|minus|disable|delete|erase|bother)\b", re.I
)

#: Hedged, questioning or reluctant. Not a refusal, and emphatically not a yes. These
#: are the dangerous ones: several contain an agreement word while meaning "maybe".
_UNSURE = re.compile(
    r"\bnot sure\b|\bmaybe\b|\bi guess\b|\bi suppose\b|\bif i have to\b"
    r"|\bwhat happens\b|\brepeat that\b|\bdoes it have to\b"
    r"|\bwhat was the question\b|\bhave to be\b",
    re.I,
)


#: How many hesitations are waited through before a consent reply is judged the usual
#: way, so a candidate who never answers cannot hold a silent call open until the time
#: limit. What counts as a hesitation lives in hesitation.py, shared with scoring.
MAX_HESITATIONS_BEFORE_CONSENT = 2


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
    if _CONTRAST.search(text) and _RECORDING.search(text):
        # Agreement with a condition on the recording is not a clear yes to it.
        return False
    if _RECORDING.search(text) and _OPPOSED.search(text):
        # A word against the recording, even without a contrast word, is not a clear yes.
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
    #: When consent was settled, and when the interview wrapped up. The part of the call
    #: between them is the interview, and it is the only part that gets scored.
    interview_started_s: Optional[float] = None
    wrapped_up_s: Optional[float] = None


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
        #: Hesitations waited through before consent was settled.
        self._hesitations = 0
        #: When either side was last heard: agent audio, or any caller transcript.
        self._last_heard_s = 0.0
        #: The agent's reply as it streams in, and whether this one has been cut off
        #: for asking something prohibited.
        self._agent_text = ""
        self._redirected = False

    # --- lifecycle ------------------------------------------------------------

    def start(self) -> List[Action]:
        """The opening. Disclosure and the consent request, both mandatory and both
        literals rather than anything the model chose."""
        self._asked_consent = True
        return self._say(self.greeting, 0.0)

    def tick(self, t_s: float) -> List[Action]:
        """The clock, with nothing said. Call it on every frame.

        The time limit was only checked when an event arrived. A candidate who went
        quiet while the agent was not speaking produced no events, so nothing ended
        the call: a mock call with the candidate silent after one answer ran to 1029
        seconds against a 900 second limit.
        """
        if self.record.ended:
            return []
        if self.engine.is_over(t_s):
            return self._end("time limit reached")
        if (
            self.record.consent is None
            and self._asked_consent
            and t_s - self._last_heard_s >= CONSENT_ANSWER_TIMEOUT_S
        ):
            # Consent was only ever settled by an answer. A candidate who never gave one
            # kept a recorded call open for the full fifteen minutes with no consent.
            self.record.consent = False
            self.engine.note_consent(False)
            actions = self._say(CONSENT_UNANSWERED, t_s)
            actions.extend(self._end("no answer to the consent question"))
            return actions
        if (
            self.record.consent is True
            and not self._wrapped
            and self.engine.should_wrap_up(t_s)
            and t_s - self._last_heard_s >= QUIET_BEFORE_WRAP_UP_S
        ):
            # The wrap-up waited for a caller turn, so a candidate who had gone quiet
            # reached the limit without being told the interview was closing, and the
            # call simply stopped. Only once both sides have been quiet for a moment,
            # so it never lands across the agent's sentence or the candidate's pause.
            self._wrapped = True
            self.record.wrapped_up_s = t_s
            return self._say(WRAP_UP, t_s)
        return []

    def on_event(self, event, t_s: float) -> List[Action]:
        """Translate one backend event into what should happen next."""
        if self.record.ended:
            return []

        if isinstance(event, (AgentAudio, UserTranscript)):
            self._last_heard_s = max(self._last_heard_s, t_s)

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
            self._agent_text = ""
            # A backend echoes back what it spoke, including the fixed utterances we
            # handed it with say(). Recording both put the greeting in the transcript
            # twice. The echo is a confirmation, not a second turn.
            # Recorded before the guard runs, so a question and the line that cut it
            # off appear in the order the candidate heard them.
            if not self._already_recorded(event.text):
                self.record.transcript.append(Turn(t_s, "agent", event.text))
                self.engine.note_agent(event.text, t_s)
            redirect = [] if self._redirected else self._guard_agent(event.text, t_s)
            self._redirected = False
            return redirect

        if isinstance(event, AgentText):
            # The model speaks for itself, so the gate cannot stop a prohibited question
            # before it is asked: by the time we have the words, the candidate is
            # hearing them. Watching the text as it streams is what makes cutting it
            # off possible at all.
            self._agent_text += event.text
            if self._redirected:
                return []
            return self._guard_agent(self._agent_text, t_s)

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
            if is_hesitation(text) and self._hesitations < MAX_HESITATIONS_BEFORE_CONSENT:
                # Not an answer yet. Waiting grants no more consent than declining does,
                # and declining ended the interview for someone who was still thinking.
                self._hesitations += 1
                return []
            return self._resolve_consent(text, t_s)

        # A hesitation mid-interview is the candidate thinking, not answering. Counted as
        # an answer it used up the outstanding probe, so every later answer was credited
        # to the wrong question, and it could revive a stalled ladder or trigger a rollover.
        hesitation = is_hesitation(text)
        if not hesitation:
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
                self.record.wrapped_up_s = t_s
                actions.extend(self._say(WRAP_UP, t_s))
            # Past the wrap-up the interview is closing: the candidate's questions, next
            # steps, thanks. Only the answer that triggered the wrap-up used to stop here.
            # Every later answer fell through and issued a fresh probe, so the agent said
            # it was out of time and then asked what broke afterwards, even in reply to
            # the candidate asking a question of their own. It could also roll the
            # session and pay for a pause in the last minute and a half.
            return actions

        if hesitation:
            # Leave the outstanding question outstanding and the session as it is.
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

    def _guard_agent(self, text: str, t_s: float) -> List[Action]:
        """Cut the agent off if it has started asking something it must not ask.

        The block list gates our own fixed lines before they are spoken. It cannot do
        that for the model's own speech, which is already in the candidate's ear by the
        time the words reach us. So this is the second line: say a fixed redirect, which
        cancels the model's reply, and put it on the record. A false positive costs one
        changed subject; a missed one is a prohibited question asked in full.
        """
        violation = check(text)
        if violation is None:
            return []
        self._redirected = True
        # What the record can honestly claim. Saying a line cancels the model's reply,
        # but how much of the question the candidate heard depends on how far ahead the
        # audio was, and a backend that reports a reply in one piece may report it only
        # once it has been spoken. "Cut off" was a stronger claim than we can make.
        self.record.flags.append(
            "The agent asked a prohibited question (%s): %r. A redirect was spoken over "
            "it, so the candidate may have heard part of it."
            % (violation.category, violation.matched)
        )
        actions = self._say(PROHIBITED_REDIRECT, t_s)
        # Telling the model is the difference between one blocked question and the same
        # question again on the next turn. The system prompt already forbids the topic
        # and it asked anyway, so the standing instruction is not enough on its own.
        actions.append(
            Brief(
                "You just started asking about %s. That subject is prohibited: never "
                "return to it. Ask about the technical work instead."
                % violation.category.replace("_", " ")
            )
        )
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
        self.record.interview_started_s = t_s
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

    def seed(self, t_s: float) -> SessionSeed:
        """What a fresh session should be primed with, as of now.

        Public because a rollover is performed later than it is asked for: it waits for
        both sides to stop talking, and by then the agent has usually asked the question
        the new session most needs to know about.
        """
        return self._seed(t_s)

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
