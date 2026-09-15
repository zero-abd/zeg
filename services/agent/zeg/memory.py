"""Working around a model that remembers about two minutes.

The model holds roughly two minutes of audio context. An interview runs fifteen. Three
mechanisms answer that, in increasing cost:

1. **Briefing.** A short restatement handed back at a turn boundary. Cheap, and the
   engine already produces it.
2. **Rollover.** Open a fresh session, prime it with everything that matters, swap at a
   turn boundary. Costs a prefill and a beat of silence.
3. **The transcript.** Our record, not the model's. Scoring reads this, so whatever the
   model forgets is still scored correctly.

This module owns the second one: when to roll, and what to prime the new session with.

Rolling is not free and it is not invisible. The candidate hears a pause. So the policy
is conservative: never mid-response, never twice in quick succession, and never while a
probe is still descending, because dropping a session mid-ladder loses the thread the
interview was following.
"""

from dataclasses import dataclass
from typing import List, Optional, Sequence

from .hesitation import is_hesitation

#: 80 ms frames, so 12.5 per second of conversation.
FRAMES_PER_SECOND = 12.5


@dataclass
class RolloverPolicy:
    """When to start a fresh model session.

    Every number here is a starting point, not a measurement. The real rollover point
    needs the box: too early wastes prefills, too late and the model has already
    forgotten what the briefing was meant to reinforce. A mistuned rollover is a worse
    experience than a forgetful agent, which is why the default errs early.
    """

    #: Roll before the model's context horizon, not at it. Leaves room for the current
    #: exchange to finish inside the window it was started in.
    context_horizon_s: float = 100.0

    #: Do not roll again immediately. Guards against a pathological loop where every
    #: turn triggers a rollover and the candidate hears nothing but pauses.
    min_session_s: float = 45.0

    #: Hard cap on one session, imposed by the runtime. Rolling well before it is
    #: reached keeps the cap from ever arriving mid-sentence.
    frame_budget: int = 12_000

    #: Roll once the session has used this share of its frames, whatever the clock says.
    frame_headroom: float = 0.8

    def should_roll(
        self,
        session_age_s: float,
        at_turn_boundary: bool,
        probe_in_progress: bool = False,
        frames_used: Optional[int] = None,
    ) -> bool:
        if not at_turn_boundary:
            return False
        if session_age_s < self.min_session_s:
            return False
        if probe_in_progress:
            # Mid-ladder is the worst moment: the thread being followed is exactly what
            # a fresh session would lose. Wait for the ladder to finish.
            return False
        if session_age_s >= self.context_horizon_s:
            return True
        if frames_used is not None:
            return frames_used >= self.frame_budget * self.frame_headroom
        return False

    def frames_for(self, seconds: float) -> int:
        return int(seconds * FRAMES_PER_SECOND)


@dataclass
class SessionSeed:
    """What a fresh session is primed with.

    Not a transcript replay. The point is to restore the working set: where we are, what
    the candidate has claimed, what still needs evidence, and the standing instructions
    that were never the model's to forget.
    """

    system_prompt: str
    briefing: str
    last_exchange: Sequence[str] = ()

    def context(self) -> str:
        """Everything except the standing instructions.

        A fresh session is started with the system prompt, so this is what it is
        steered with afterwards. Sending the prompt twice would spend a prefill on
        text the session already holds.
        """
        parts = ["Where we are:", self.briefing]
        if self.last_exchange:
            parts.append("")
            parts.append("The last thing said, so you can pick up naturally:")
            for line in self.last_exchange:
                parts.append("  %s" % line)
        return "\n".join(parts)

    def render(self) -> str:
        return "\n".join([self.system_prompt.rstrip(), "", self.context()])


def last_exchange(transcript: Sequence) -> List[str]:
    """The last question and everything the candidate said back, rendered for a seed.

    At most two lines. Enough to continue without a seam the candidate can hear, short
    enough that the prefill stays cheap.

    It used to be the last two turns, whoever spoke them. A candidate who paused
    mid-answer, or said "um" first, fills both, so the fresh session was handed half an
    answer and never the question it answered. The candidate's replies since the last
    agent line are joined into one, and hesitations are left out.
    """
    replies: List[str] = []
    question = None
    for t in reversed(list(transcript)):
        if t.speaker == "agent":
            question = t.text
            break
        if t.speaker == "caller" and not is_hesitation(t.text):
            replies.append(t.text)
    out = []
    if question is not None:
        out.append("Interviewer: %s" % shorten(question))
    if replies:
        out.append("Candidate: %s" % shorten(" ".join(reversed(replies))))
    return out


def shorten(text: str, limit: int = 160) -> str:
    """Shorten from the middle.

    An answer ends on its point: "which took p99 from 400 milliseconds down to 30". Cut
    from the end, the seed kept the lead-in and lost the figure the next question
    follows up on.
    """
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    head = limit // 3
    tail = limit - head - 3
    return "%s … %s" % (text[:head].rstrip(), text[-tail:].lstrip())
