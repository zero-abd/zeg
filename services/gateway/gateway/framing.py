"""Rechunk a PCM stream into exact 20 ms frames.

A resampler hands back audio in whatever block size it likes; the VoiceSession
wants frames of a fixed duration (`AudioConfig.frame_ms`, 20 ms). This holds the
ragged remainder between calls so no samples are dropped or duplicated at block
boundaries, and stamps each frame with its position in the call.

Pure stdlib, matching services/agent/zeg/audio.py: no numpy on the audio path.
"""

from typing import List

from zeg.audio import AudioFrame, BYTES_PER_SAMPLE
from zeg.config import INPUT_SAMPLE_RATE, FRAME_MS


class FrameChunker:
    """Accumulates PCM16 bytes and emits whole `frame_ms` frames."""

    def __init__(self, sample_rate: int = INPUT_SAMPLE_RATE, frame_ms: int = FRAME_MS) -> None:
        self.sample_rate = sample_rate
        self.frame_ms = frame_ms
        self.frame_samples = sample_rate * frame_ms // 1000
        self.frame_bytes = self.frame_samples * BYTES_PER_SAMPLE
        self._buf = bytearray()
        self._emitted_samples = 0

    def push(self, pcm: bytes) -> List[AudioFrame]:
        """Add bytes, return every complete frame now available."""
        self._buf.extend(pcm)
        out: List[AudioFrame] = []
        while len(self._buf) >= self.frame_bytes:
            chunk = bytes(self._buf[: self.frame_bytes])
            del self._buf[: self.frame_bytes]
            out.append(
                AudioFrame(chunk, self.sample_rate, self._emitted_samples / self.sample_rate)
            )
            self._emitted_samples += self.frame_samples
        return out

    @property
    def pending_samples(self) -> int:
        return len(self._buf) // BYTES_PER_SAMPLE
