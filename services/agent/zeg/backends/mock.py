"""A backend that runs anywhere.

It exists so the conversation harness, the interview engine and the tests can be
developed and run without a GB10 box. It imitates the *shape* of the real model's
behaviour: full duplex, partial then final transcripts, barge-in, streamed audio at
22.05 kHz. It imitates none of its intelligence.

Replies come from a script. Nothing here should ever be mistaken for a measurement
of the real model.
"""

import math
import re
from typing import Iterator, List, Optional, Sequence

from ..audio import AudioFrame, rms, tone
from ..config import AudioConfig
from .base import (
    AgentAudio,
    AgentInterrupted,
    AgentText,
    BackendEvent,
    UserTranscript,
    VoiceBackend,
    VoiceSession,
)

#: Above this RMS the mock treats a frame as speech. Real VAD is a model, not a
#: threshold, but a threshold is enough to exercise barge-in.
SPEECH_RMS = 0.02

#: Speaking rate used to convert reply text into a plausible number of audio frames.
WORDS_PER_MINUTE = 150.0


class ScriptedSession(VoiceSession):
    def __init__(
        self,
        system_prompt: str,
        greeting: Optional[str],
        script: Sequence[str],
        audio: AudioConfig,
        latency_frames: int = 5,
    ) -> None:
        self.system_prompt = system_prompt
        self._script = list(script)
        self._audio = audio
        self._latency_frames = latency_frames

        self.steers: List[str] = []
        self._pending: List[BackendEvent] = []
        self._speaking: List[AudioFrame] = []
        self._phase = 0.0
        self._elapsed_s = 0.0
        self._closed = False

        # Caller-speech bookkeeping, used for endpointing and barge-in.
        self._heard_frames = 0
        self._silence_frames = 0
        self._in_utterance = False
        self._countdown = 0

        if greeting:
            self._begin_reply(greeting)

    # --- VoiceSession ---------------------------------------------------------

    def push_audio(self, frame: AudioFrame) -> None:
        if self._closed:
            raise RuntimeError("session is closed")
        self._elapsed_s += frame.duration_s

        loud = rms(frame) >= SPEECH_RMS
        if loud:
            # Barge-in: the caller talking while the agent speaks cancels playback.
            if self.is_speaking:
                self._speaking.clear()
                self._countdown = 0
                self._pending.append(AgentInterrupted())
            self._heard_frames += 1
            self._silence_frames = 0
            if not self._in_utterance:
                self._in_utterance = True
            elif self._heard_frames % 10 == 0:
                self._pending.append(UserTranscript(self._partial(), final=False))
        elif self._in_utterance:
            self._silence_frames += 1
            # Endpoint after roughly 200 ms of silence, matching the latency budget.
            if self._silence_frames * self._audio.frame_ms >= 200:
                self._end_utterance()

        # Stream the reply out one frame per inbound frame, which is what keeps the
        # agent interruptible. Emitting a whole reply at once would make barge-in
        # untestable, because there would be nothing left to cancel.
        if self._countdown > 0:
            self._countdown -= 1
        elif self._speaking:
            self._pending.append(AgentAudio(self._speaking.pop(0)))

    def say(self, text: str) -> None:
        """Speak fixed text. Replaces anything queued, because the caller asked for
        this utterance now and a half-finished previous one is not wanted behind it."""
        if self._closed:
            raise RuntimeError("session is closed")
        self._speaking.clear()
        self._begin_reply(text)

    def steer(self, text: str) -> None:
        """Recorded, never spoken. The mock has no context to put it in, so the only
        thing worth asserting is that it does not reach the audio path."""
        if self._closed:
            raise RuntimeError("session is closed")
        self.steers.append(text)

    def poll(self) -> Iterator[BackendEvent]:
        out, self._pending = self._pending, []
        for ev in out:
            yield ev

    def close(self) -> None:
        self._closed = True
        self._pending.clear()
        self._speaking.clear()

    # --- internals ------------------------------------------------------------

    def _partial(self) -> str:
        spoken_s = self._heard_frames * self._audio.frame_ms / 1000.0
        n = max(1, int(spoken_s * WORDS_PER_MINUTE / 60.0))
        return " ".join(["word"] * n)

    def _end_utterance(self) -> None:
        self._pending.append(UserTranscript(self._partial(), final=True))
        self._in_utterance = False
        self._heard_frames = 0
        self._silence_frames = 0
        if self._script:
            self._begin_reply(self._script.pop(0))

    def _begin_reply(self, text: str) -> None:
        """Queue a reply and start the clock on its first audio.

        The delay models time-to-first-audio. It is a constant here; on real hardware
        it is prefill plus the TTS decoder's first chunk.
        """
        self._speaking = self._synthesise(text)
        self._pending.append(AgentText(text, final=True))
        self._countdown = self._latency_frames

    @property
    def is_speaking(self) -> bool:
        return bool(self._speaking) or self._countdown > 0

    @property
    def caller_speaking(self) -> bool:
        return self._in_utterance

    @property
    def agent_speaking(self) -> bool:
        return self.is_speaking

    def _synthesise(self, text: str) -> List[AudioFrame]:
        """Turn text into the right *amount* of audio at the right rate.

        A 220 Hz tone, not speech. Its only jobs are to occupy the correct duration
        and to prove the playback path handles 22.05 kHz frames.
        """
        words = max(1, len(re.findall(r"\S+", text)))
        duration_s = words / (WORDS_PER_MINUTE / 60.0)
        rate = self._audio.output_sample_rate
        per_frame = self._audio.output_frame_samples
        n_frames = max(1, int(math.ceil(duration_s * rate / per_frame)))

        frames = []
        t = self._elapsed_s
        for _ in range(n_frames):
            f = tone(rate, per_frame, phase=self._phase)
            self._phase = (self._phase + 2 * math.pi * 220.0 * per_frame / rate) % (
                2 * math.pi
            )
            frames.append(AudioFrame(f.pcm, rate, t))
            t += per_frame / rate
        return frames


DEFAULT_SCRIPT = [
    "Thanks. Tell me about the hardest bug you shipped a fix for this year.",
    "What did you personally do there, as opposed to the rest of the team?",
    "Do you remember roughly what the throughput was before and after?",
    "What did you give up to get that? Every fix costs something.",
    "Last one. What broke afterwards that you did not expect?",
    "That is my time. Thanks for talking me through it.",
]


class MockBackend(VoiceBackend):
    name = "mock"

    def __init__(
        self,
        audio: Optional[AudioConfig] = None,
        script: Optional[Sequence[str]] = None,
        latency_frames: int = 5,
    ) -> None:
        self._audio = audio or AudioConfig()
        self._script = list(script) if script is not None else list(DEFAULT_SCRIPT)
        self._latency_frames = latency_frames

    def start_session(
        self, system_prompt: str, greeting: Optional[str] = None
    ) -> VoiceSession:
        return ScriptedSession(
            system_prompt=system_prompt,
            greeting=greeting,
            script=self._script,
            audio=self._audio,
            latency_frames=self._latency_frames,
        )
