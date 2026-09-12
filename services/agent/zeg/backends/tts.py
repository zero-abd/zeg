"""A scripted backend that speaks real, intelligible words.

The demo fallback the docs sanction (docs/00, docs/02): instead of the real
audio-to-audio model, the agent reads *prepared* interview questions aloud with
a local text-to-speech engine. It reuses the mock backend's tested turn-taking,
endpointing and barge-in wholesale and only swaps the audio: where the mock
emits a 220 Hz tone, this emits synthesized speech.

It is not intelligent. The questions are fixed (mock.DEFAULT_SCRIPT) and it does
not understand answers; it just sounds like an interviewer. Lines are rendered
once at warmup and cached, so there is no per-turn synthesis lag in the call.

Engines, in order of preference: `say` (macOS, always present), then
`espeak-ng` / `espeak` (Linux: `apt install espeak-ng`). If none is found it
falls back to a tone rather than failing, so a demo never goes silent.
"""

import array
import os
import shutil
import subprocess
import tempfile
import wave
from typing import Dict, List, Optional, Sequence

from ..audio import AudioFrame, resample_linear, tone
from ..config import AudioConfig
from .base import VoiceBackend, VoiceSession
from .mock import DEFAULT_SCRIPT, ScriptedSession


def _which_engine() -> Optional[str]:
    for name in ("say", "espeak-ng", "espeak"):
        if shutil.which(name):
            return name
    return None


def _render_wav(text: str, engine: str, path: str) -> None:
    if engine == "say":
        subprocess.run(
            ["say", "--file-format=WAVE", "--data-format=LEI16@22050", "-o", path, text],
            check=True, capture_output=True,
        )
    else:  # espeak-ng / espeak both write a 22.05 kHz mono 16-bit WAV with -w
        subprocess.run([engine, "-s", "165", "-w", path, text], check=True, capture_output=True)


def _to_mono(pcm: bytes, channels: int) -> bytes:
    if channels <= 1:
        return pcm
    a = array.array("h")
    a.frombytes(pcm)
    return array.array("h", a[::channels]).tobytes()  # take the first channel


def _reframe(pcm: bytes, rate: int, per_samples: int) -> List[AudioFrame]:
    fb = per_samples * 2
    frames: List[AudioFrame] = []
    t = 0.0
    for off in range(0, len(pcm), fb):
        chunk = pcm[off:off + fb]
        if len(chunk) < fb:
            chunk = chunk + b"\x00" * (fb - len(chunk))
        frames.append(AudioFrame(chunk, rate, t))
        t += per_samples / rate
    return frames or [AudioFrame(b"\x00" * fb, rate, 0.0)]


def synth_frames(text: str, audio: AudioConfig, engine: Optional[str]) -> List[AudioFrame]:
    """Render one line to output-rate 20 ms frames. Never raises: tone on failure."""
    rate = audio.output_sample_rate
    per = audio.output_frame_samples
    if engine:
        try:
            fd, path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            _render_wav(text, engine, path)
            with wave.open(path, "rb") as w:
                ch, sw, sr = w.getnchannels(), w.getsampwidth(), w.getframerate()
                pcm = w.readframes(w.getnframes())
            os.unlink(path)
            if sw == 2 and pcm:
                pcm = _to_mono(pcm, ch)
                if sr != rate:
                    pcm = resample_linear(AudioFrame(pcm, sr), rate).pcm
                return _reframe(pcm, rate, per)
        except Exception:  # noqa: BLE001 - a demo must not crash on a TTS hiccup
            pass
    # Fallback: a tone sized to the text, so timing/lifecycle still work.
    words = max(1, len(text.split()))
    n = max(1, int(round(words / 2.5 * rate / per)))  # ~150 wpm
    return [AudioFrame(tone(rate, per).pcm, rate, i * per / rate) for i in range(n)]


class TTSSession(ScriptedSession):
    """A ScriptedSession whose 'voice' is real speech instead of a tone."""

    def __init__(self, system_prompt, greeting, script, audio, cache, engine, latency_frames=3):
        self._cache = cache
        self._engine = engine
        super().__init__(system_prompt, greeting, script, audio, latency_frames)

    def _synthesise(self, text: str) -> List[AudioFrame]:
        frames = self._cache.get(text)
        if frames is None:
            frames = synth_frames(text, self._audio, self._engine)
            self._cache[text] = frames
        # Restamp timestamps from the current call position; pcm is shared (frozen).
        t = self._elapsed_s
        out = []
        for fr in frames:
            out.append(AudioFrame(fr.pcm, fr.sample_rate, t))
            t += fr.n_samples / fr.sample_rate
        return out


class TTSBackend(VoiceBackend):
    name = "tts"

    def __init__(self, audio: Optional[AudioConfig] = None,
                 script: Optional[Sequence[str]] = None, latency_frames: int = 3) -> None:
        self._audio = audio or AudioConfig()
        self._script = list(script) if script is not None else list(DEFAULT_SCRIPT)
        self._latency_frames = latency_frames
        self._engine = _which_engine()
        self._cache: Dict[str, List[AudioFrame]] = {}

    def warmup(self) -> None:
        """Pre-render the fixed lines so no synthesis happens mid-call."""
        from ..prompts import GREETING
        for text in [GREETING] + self._script:
            if text not in self._cache:
                self._cache[text] = synth_frames(text, self._audio, self._engine)

    def start_session(self, system_prompt: str, greeting: Optional[str] = None) -> VoiceSession:
        return TTSSession(system_prompt, greeting, self._script, self._audio,
                          self._cache, self._engine, self._latency_frames)
