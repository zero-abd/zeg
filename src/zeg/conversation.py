"""The conversation harness.

Drives a simulated caller against a backend and records what happened: the
transcript, the audio the agent produced, and a per-turn latency histogram.

The clock is virtual. Time advances by the duration of each frame pushed, not by
wall clock, so a 15-minute call replays in under a second and the latency numbers
are deterministic. That makes this usable as a regression test. It also means the
numbers measure *the pipeline's frame accounting*, not the hardware. Real latency
comes from the GB10 backend under a real clock; see docs/03-latency-budget.md.
"""

import statistics
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from .audio import AudioFrame, tone
from .backends.base import (
    AgentAudio,
    AgentInterrupted,
    AgentText,
    BackendError,
    UserTranscript,
    VoiceBackend,
)
from .config import AudioConfig, CallConfig


@dataclass
class CallerTurn:
    """One thing the simulated caller does.

    `speak_s` is how long they talk; `pause_after_s` is the silence that follows and
    lets the endpointer fire. `barge_in` makes them start talking while the agent is
    still going.
    """

    text: str
    speak_s: float = 3.0
    pause_after_s: float = 1.0
    barge_in: bool = False


@dataclass
class TranscriptEntry:
    at_s: float
    speaker: str  # "agent" | "caller"
    text: str


@dataclass
class CallResult:
    transcript: List[TranscriptEntry] = field(default_factory=list)
    agent_audio_frames: int = 0
    agent_audio_s: float = 0.0
    interruptions: int = 0
    duration_s: float = 0.0
    reply_latencies_ms: List[float] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    hit_time_limit: bool = False

    @property
    def p95_latency_ms(self) -> Optional[float]:
        """p95, not the mean. The mean hides the turns that ruin calls."""
        if not self.reply_latencies_ms:
            return None
        ordered = sorted(self.reply_latencies_ms)
        idx = min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))
        return ordered[idx]

    @property
    def median_latency_ms(self) -> Optional[float]:
        if not self.reply_latencies_ms:
            return None
        return statistics.median(self.reply_latencies_ms)

    def render(self) -> str:
        lines = []
        for e in self.transcript:
            m, s = divmod(int(e.at_s), 60)
            lines.append("[%02d:%02d] %-6s %s" % (m, s, e.speaker, e.text))
        return "\n".join(lines)


DEFAULT_CALLER: Sequence[CallerTurn] = (
    CallerTurn("yes that is fine", speak_s=1.5),
    CallerTurn("a race condition in our payment reconciler", speak_s=4.0),
    CallerTurn("i wrote the fix and the repro harness", speak_s=3.5),
    CallerTurn("about twelve hundred a second before, forty thousand after", speak_s=4.5),
    CallerTurn("we gave up strict ordering across shards", speak_s=3.5, barge_in=True),
    CallerTurn("a downstream report started double counting", speak_s=4.0),
)


class ConversationRunner:
    def __init__(
        self,
        backend: VoiceBackend,
        audio: Optional[AudioConfig] = None,
        call: Optional[CallConfig] = None,
    ) -> None:
        self.backend = backend
        self.audio = audio or AudioConfig()
        self.call = call or CallConfig()

    def run(
        self,
        system_prompt: str,
        greeting: str,
        caller: Sequence[CallerTurn] = DEFAULT_CALLER,
    ) -> CallResult:
        result = CallResult()
        clock = _VirtualClock(self.audio.frame_ms)
        session = self.backend.start_session(system_prompt, greeting=greeting)

        try:
            for turn in caller:
                if not turn.barge_in:
                    # Wait out whatever the agent is still saying, then speak.
                    self._drain_agent(session, clock, result)
                    if result.hit_time_limit:
                        break

                self._speak(session, clock, result, turn)
                if result.hit_time_limit:
                    break

                # Silence after the turn is what lets the endpointer fire.
                self._silence(session, clock, result, turn.pause_after_s,
                              measure_from=clock.now)

            self._drain_agent(session, clock, result)
        finally:
            session.close()

        result.duration_s = clock.now
        return result

    # --- caller behaviours ----------------------------------------------------

    def _speak(self, session, clock, result, turn: CallerTurn) -> None:
        n = int(turn.speak_s * 1000 / self.audio.frame_ms)
        for _ in range(n):
            if self._over_time(clock, result):
                return
            f = tone(
                self.audio.input_sample_rate,
                self.audio.input_frame_samples,
                freq_hz=180.0,
                amplitude=0.3,
            )
            session.push_audio(AudioFrame(f.pcm, f.sample_rate, clock.now))
            clock.tick()
            self._consume(session, clock, result)
        result.transcript.append(TranscriptEntry(clock.now, "caller", turn.text))

    def _silence(self, session, clock, result, seconds: float,
                 measure_from: Optional[float] = None) -> None:
        """Push silence and time how long until the agent's first audio."""
        n = int(seconds * 1000 / self.audio.frame_ms)
        start = clock.now if measure_from is None else measure_from
        measured = False
        for _ in range(n):
            if self._over_time(clock, result):
                return
            session.push_audio(
                AudioFrame.silence(
                    self.audio.input_sample_rate,
                    self.audio.input_frame_samples,
                    clock.now,
                )
            )
            clock.tick()
            before = result.agent_audio_frames
            self._consume(session, clock, result)
            if not measured and result.agent_audio_frames > before:
                result.reply_latencies_ms.append((clock.now - start) * 1000.0)
                measured = True

    def _drain_agent(self, session, clock, result, max_s: float = 30.0) -> None:
        """Push silence until the agent stops producing audio."""
        idle = 0
        limit = int(max_s * 1000 / self.audio.frame_ms)
        for _ in range(limit):
            if self._over_time(clock, result):
                return
            session.push_audio(
                AudioFrame.silence(
                    self.audio.input_sample_rate,
                    self.audio.input_frame_samples,
                    clock.now,
                )
            )
            clock.tick()
            before = result.agent_audio_frames
            self._consume(session, clock, result)
            idle = 0 if result.agent_audio_frames > before else idle + 1
            if idle >= 10:
                return

    # --- plumbing -------------------------------------------------------------

    def _consume(self, session, clock, result) -> None:
        for ev in session.poll():
            if isinstance(ev, AgentAudio):
                result.agent_audio_frames += 1
                result.agent_audio_s += ev.frame.duration_s
            elif isinstance(ev, AgentText) and ev.final:
                result.transcript.append(
                    TranscriptEntry(clock.now, "agent", ev.text)
                )
            elif isinstance(ev, AgentInterrupted):
                result.interruptions += 1
            elif isinstance(ev, BackendError):
                result.errors.append(ev.message)
            elif isinstance(ev, UserTranscript):
                pass  # the caller's words come from the script, not the model

    def _over_time(self, clock, result) -> bool:
        if clock.now >= self.call.max_duration_s:
            result.hit_time_limit = True
            return True
        return False


class _VirtualClock:
    def __init__(self, frame_ms: int) -> None:
        self.now = 0.0
        self._step = frame_ms / 1000.0

    def tick(self) -> None:
        self.now += self._step
