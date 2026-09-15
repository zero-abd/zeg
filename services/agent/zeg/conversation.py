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


# --- Driven by the interview engine ------------------------------------------


@dataclass
class DrivenResult:
    """What a driven call produced, on top of the raw audio accounting."""

    transcript: List[TranscriptEntry] = field(default_factory=list)
    steers: List[str] = field(default_factory=list)
    probes: List[str] = field(default_factory=list)
    rollovers: int = 0
    agent_audio_frames: int = 0
    #: Turn boundaries the harness had to supply because the backend reported none.
    #: Non-zero means the backend is playback, not recognition.
    synthesised_turns: int = 0
    flags: List[str] = field(default_factory=list)
    consent: Optional[bool] = None
    ended: Optional[str] = None
    duration_s: float = 0.0
    interruptions: int = 0

    def render(self) -> str:
        lines = []
        for e in self.transcript:
            m, s = divmod(int(e.at_s), 60)
            lines.append("[%02d:%02d] %-6s %s" % (m, s, e.speaker, e.text))
        return "\n".join(lines)


class InterviewRunner:
    """Runs a simulated caller against a backend with the interview engine in charge.

    The difference from `ConversationRunner` is who decides what happens. There, the
    backend's own script drives and the runner just measures. Here the engine owns
    consent, the clock, the briefings and the rollovers, and the backend is only a
    voice. That is the arrangement the real system uses, so this is the one that finds
    integration bugs.
    """

    def __init__(
        self,
        backend: VoiceBackend,
        interview=None,
        audio: Optional[AudioConfig] = None,
    ) -> None:
        from .interview import Interview  # local: avoids a cycle at import time

        self.backend = backend
        self.audio = audio or AudioConfig()
        self.interview = interview or Interview()

    def run(self, caller: Sequence[CallerTurn] = DEFAULT_CALLER) -> DrivenResult:
        from .interview import Brief, EndCall, Probe, Rollover, Speak

        result = DrivenResult()
        clock = _VirtualClock(self.audio.frame_ms)
        # The session is instance state, not a local, because a rollover replaces it
        # mid-call. Passing it down as an argument meant the loops kept pushing audio
        # into the session that had just been closed.
        self._session = self.backend.start_session(self.interview.system_prompt)
        # What the simulated caller is currently saying. It has to outlive the speech
        # itself, because the endpoint fires during the silence that follows.
        self._saying: Optional[str] = None

        def perform(actions):
            for a in actions:
                if isinstance(a, Speak):
                    self._session.say(a.text)
                elif isinstance(a, Brief):
                    result.steers.append(a.text)
                    self._session.steer(a.text)
                elif isinstance(a, Probe):
                    result.probes.append(a.instruction)
                    self._session.steer(a.instruction)
                elif isinstance(a, Rollover):
                    result.rollovers += 1
                    self._roll(a.seed)
                elif isinstance(a, EndCall):
                    result.ended = a.reason

        try:
            perform(self.interview.start())
            for turn in caller:
                if result.ended:
                    break
                if not turn.barge_in:
                    # A polite caller waits for the agent to finish. One who barges in
                    # starts talking over it, which is the case the media path has to
                    # get right.
                    self._drain(clock, result, perform)
                if result.ended:
                    break
                self._speak(clock, result, perform, turn)
                self._silence(clock, result, perform, turn.pause_after_s)
            if not result.ended:
                self._drain(clock, result, perform)
        finally:
            self._session.close()

        result.transcript = [
            TranscriptEntry(t.at_s, t.speaker, t.text)
            for t in self.interview.record.transcript
        ]
        result.flags = list(self.interview.record.flags)
        result.consent = self.interview.record.consent
        result.duration_s = clock.now
        return result

    def _roll(self, seed) -> None:
        """Swap in a fresh session primed with `seed`.

        Close first, then open. The box runs one conversation at a time, in the backend
        and again in the server, so opening first raised on the first rollover of every
        long call. The candidate hears a beat of silence either way.
        """
        self._session.close()
        self._session = self.backend.start_session(seed.system_prompt)
        # The whole seed, not just the briefing. The last exchange is what lets the new
        # session pick up mid-thought rather than start the topic over.
        self._session.steer(seed.context())

    # --- caller behaviours ----------------------------------------------------

    def _speak(self, clock, result, perform, turn: CallerTurn) -> None:
        n = int(turn.speak_s * 1000 / self.audio.frame_ms)
        for _ in range(n):
            f = tone(self.audio.input_sample_rate, self.audio.input_frame_samples,
                     freq_hz=180.0, amplitude=0.3)
            self._session.push_audio(AudioFrame(f.pcm, f.sample_rate, clock.now))
            self._saying = turn.text
            clock.tick()
            self._consume(clock, result, perform)

    def _silence(self, clock, result, perform, seconds: float) -> None:
        for _ in range(int(seconds * 1000 / self.audio.frame_ms)):
            self._session.push_audio(
                AudioFrame.silence(self.audio.input_sample_rate,
                                   self.audio.input_frame_samples, clock.now))
            clock.tick()
            self._consume(clock, result, perform)
        self._deliver_pending(clock, result, perform)

    def _deliver_pending(self, clock, result, perform) -> None:
        """Tell the interview the caller finished, if the backend never did.

        A backend that cannot recognise speech reports no end of turn, and the engine
        then sees only its own voice: consent is never resolved, no probe is issued,
        nothing downstream of a candidate turn happens at all. The transcript still
        looks plausible, which is what makes it dangerous.

        The simulated caller knows what it said and when it stopped, so the harness
        supplies the boundary itself. A backend that does report one gets there first
        and this finds nothing left to deliver.
        """
        from .backends.base import UserTranscript

        if self._saying is None:
            return
        text, self._saying = self._saying, None
        result.synthesised_turns += 1
        perform(self.interview.on_event(UserTranscript(text, final=True), clock.now))

    def _drain(self, clock, result, perform, max_s: float = 40.0) -> None:
        """Wait for the agent to stop speaking.

        Watch the audio, not the transcript. The transcript grows once per utterance,
        which happens the moment the agent starts, so draining on it returned while
        there were still seconds of speech queued and the caller then talked over every
        single turn.
        """
        idle = 0
        for _ in range(int(max_s * 1000 / self.audio.frame_ms)):
            before = result.agent_audio_frames
            self._session.push_audio(
                AudioFrame.silence(self.audio.input_sample_rate,
                                   self.audio.input_frame_samples, clock.now))
            clock.tick()
            self._consume(clock, result, perform)
            idle = 0 if result.agent_audio_frames > before else idle + 1
            if idle >= 15:
                return

    def _consume(self, clock, result, perform) -> None:
        from .backends.base import AgentAudio, AgentInterrupted, UserTranscript

        source = self._session
        for ev in source.poll():
            if isinstance(ev, AgentAudio):
                result.agent_audio_frames += 1
            if isinstance(ev, AgentInterrupted):
                result.interruptions += 1
            if isinstance(ev, UserTranscript) and ev.final:
                # The simulated caller supplies the words; the mock only tells us *when*
                # an utterance ended. Substituting keeps the transcript legible without
                # pretending the mock recognised anything.
                if self._saying is None:
                    continue
                ev = UserTranscript(self._saying, final=True)
                self._saying = None
            perform(self.interview.on_event(ev, clock.now))
            if self._session is not source or result.ended:
                # The session these events came from was replaced, or the call is over.
                # Anything else it had queued describes speech nobody will hear, and a
                # backend that snapshots its queue would otherwise keep delivering it.
                return
