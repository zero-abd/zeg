"""Audio primitives.

PCM is carried as signed 16-bit little-endian bytes, which is what both RTP and the
model's I/O reduce to. Numpy is deliberately absent so the mock path runs on a stock
interpreter with nothing installed.
"""

import array
import math
from dataclasses import dataclass

BYTES_PER_SAMPLE = 2


@dataclass(frozen=True)
class AudioFrame:
    """One frame of mono PCM16.

    `pcm` length must be a whole number of samples. `timestamp_s` is the frame's
    position in the call, used for latency accounting and transcript alignment.
    """

    pcm: bytes
    sample_rate: int
    timestamp_s: float = 0.0

    def __post_init__(self) -> None:
        if len(self.pcm) % BYTES_PER_SAMPLE:
            raise ValueError(
                "pcm length %d is not a whole number of 16-bit samples"
                % len(self.pcm)
            )

    @property
    def n_samples(self) -> int:
        return len(self.pcm) // BYTES_PER_SAMPLE

    @property
    def duration_s(self) -> float:
        return self.n_samples / self.sample_rate

    def samples(self) -> array.array:
        a = array.array("h")
        a.frombytes(self.pcm)
        return a

    @classmethod
    def silence(cls, sample_rate: int, n_samples: int, timestamp_s: float = 0.0):
        return cls(b"\x00" * (n_samples * BYTES_PER_SAMPLE), sample_rate, timestamp_s)

    @classmethod
    def from_samples(cls, samples, sample_rate: int, timestamp_s: float = 0.0):
        a = samples if isinstance(samples, array.array) else array.array("h", samples)
        return cls(a.tobytes(), sample_rate, timestamp_s)


def rms(frame: AudioFrame) -> float:
    """Root mean square amplitude, normalised to 0..1. Used by the crude VAD."""
    s = frame.samples()
    if not s:
        return 0.0
    total = sum(v * v for v in s)
    return math.sqrt(total / len(s)) / 32768.0


def resample_linear(frame: AudioFrame, target_rate: int) -> AudioFrame:
    """Linear-interpolation resample.

    Good enough for the mock path and for tests. The GB10 backend must not use this:
    telephone audio upsampled without a proper anti-alias filter measurably degrades
    recognition, and a transcription gap becomes a scoring gap. See docs/05.
    """
    if target_rate == frame.sample_rate:
        return frame
    src = frame.samples()
    if not src:
        return AudioFrame(b"", target_rate, frame.timestamp_s)

    ratio = target_rate / frame.sample_rate
    n_out = int(len(src) * ratio)
    out = array.array("h", [0]) * n_out
    for i in range(n_out):
        pos = i / ratio
        lo = int(pos)
        hi = min(lo + 1, len(src) - 1)
        w = pos - lo
        out[i] = int(src[lo] * (1.0 - w) + src[hi] * w)
    return AudioFrame(out.tobytes(), target_rate, frame.timestamp_s)


def tone(sample_rate: int, n_samples: int, freq_hz: float = 220.0,
         amplitude: float = 0.25, phase: float = 0.0) -> AudioFrame:
    """A sine tone. Stands in for synthesised speech in the mock backend."""
    out = array.array("h", [0]) * n_samples
    step = 2.0 * math.pi * freq_hz / sample_rate
    for i in range(n_samples):
        out[i] = int(amplitude * 32767 * math.sin(phase + i * step))
    return AudioFrame(out.tobytes(), sample_rate)
