"""Configuration.

Audio rates are dictated by the speech model we run: it consumes 16 kHz and its
synthesis stage emits 22.05 kHz, while telephony and most conferencing paths deliver
8 kHz. Checkpoint locations are deployment configuration, not source constants.
"""

from dataclasses import dataclass, field
from typing import Optional

# --- Audio -------------------------------------------------------------------

#: The model consumes 16 kHz. Telephone audio arrives at 8 kHz and must be upsampled.
INPUT_SAMPLE_RATE = 16_000

#: The model's TTS decoder emits 22.05 kHz.
OUTPUT_SAMPLE_RATE = 22_050

#: Telephony carries 8 kHz G.711 much of the time.
TELEPHONY_SAMPLE_RATE = 8_000

#: 20 ms frames, the RTP convention.
FRAME_MS = 20


def frame_samples(sample_rate: int, frame_ms: int = FRAME_MS) -> int:
    """Samples in one frame at the given rate."""
    return sample_rate * frame_ms // 1000


# --- Runtime -----------------------------------------------------------------


@dataclass
class AudioConfig:
    input_sample_rate: int = INPUT_SAMPLE_RATE
    output_sample_rate: int = OUTPUT_SAMPLE_RATE
    frame_ms: int = FRAME_MS

    @property
    def input_frame_samples(self) -> int:
        return frame_samples(self.input_sample_rate, self.frame_ms)

    @property
    def output_frame_samples(self) -> int:
        return frame_samples(self.output_sample_rate, self.frame_ms)


@dataclass
class BackendConfig:
    """How to reach the model.

    `checkpoint_dir` is a local path because nothing is downloaded at call time; the
    box is provisioned ahead of time and weights are pinned by version.
    """

    kind: str = "mock"  # "mock" | "gb10"
    checkpoint_dir: str = "/opt/zeg/weights"
    device: str = "cuda"
    dtype: str = "bfloat16"
    audio: AudioConfig = field(default_factory=AudioConfig)


@dataclass
class CallConfig:
    """Limits the interview engine enforces regardless of what the model wants."""

    max_duration_s: int = 15 * 60
    #: When to start closing. Derived from the call's length unless given: it was a fixed
    #: 810 seconds, so a 10-minute call was due to wrap up after it had already ended and
    #: the candidate was never told the interview was closing.
    wrap_up_at_s: Optional[int] = None
    silence_nudge_s: float = 4.0
    silence_rephrase_s: float = 8.0
    silence_move_on_s: float = 15.0

    def __post_init__(self) -> None:
        if self.wrap_up_at_s is None:
            # Ninety seconds for the candidate's questions and the close, but never before
            # three quarters of the call: 810 of 900, 510 of 600, 225 of 300, 45 of 60.
            self.wrap_up_at_s = int(max(self.max_duration_s * 0.75, self.max_duration_s - 90))
