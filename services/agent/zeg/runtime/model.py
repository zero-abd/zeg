"""Loading and stepping the speech model.

Nothing in this file has run on hardware. It is the shape the model wrapper has to
take, with the CUDA-dependent parts guarded and the seams that have to be filled
in on the box marked as such. Being explicit about that is more useful than code
that looks finished and is not.

What the model is, in the terms this runtime uses:

- a **speech encoder** that turns 80 ms of 16 kHz caller audio into one embedding;
- a **quantized backbone**, the large autoregressive model, which takes that
  embedding fused with what it said last frame and emits one text token per frame;
- a **synthesis decoder** that turns those text tokens into codec tokens;
- an **audio codec** that turns codec tokens into 80 ms of 22.05 kHz PCM.

All four advance in lockstep, one step per 80 ms, forever, whether or not the
agent is speaking. That is what makes the model full duplex and it is also why
this wrapper is the only thing allowed to touch it: the state is recurrent, so
two callers stepping it concurrently do not produce two conversations, they
produce one corrupted one.

Quantization is the reason it fits. Decode on this box is memory-bandwidth-bound
rather than compute-bound, so 8-bit weights buy close to linear speedup on the
backbone. The synthesis decoder is kept at higher activation precision because its
sampler is the precision-sensitive part; dropping it degrades into audible
artifacts rather than into a clean error, which is the worst failure mode there is.
"""

import os
from dataclasses import dataclass
from typing import Any, Optional

from . import codec as codec_mod
from . import protocol as p
from .session import FrameResult


class ModelUnavailable(RuntimeError):
    """The model cannot be loaded here. Carries why, so the log is actionable."""


@dataclass
class ModelPaths:
    """Where the weights are. Deployment configuration, not source constants."""

    root: str

    @property
    def backbone(self) -> str:
        return os.path.join(self.root, "backbone")

    @property
    def decoder(self) -> str:
        return os.path.join(self.root, "decoder")

    def check(self) -> None:
        for name, path in (("backbone", self.backbone), ("decoder", self.decoder)):
            if not os.path.isdir(path):
                raise ModelUnavailable(
                    "no %s weights at %s. See SETUP.local.md for the download." % (name, path)
                )


def require_cuda() -> Any:
    """Import torch and assert a usable GPU. Every CUDA path goes through here.

    The import is inside the function on purpose: importing this module on a laptop
    must stay free, because the rest of the package is developed there.
    """
    try:
        import torch  # noqa: WPS433 - deliberate lazy import
    except ImportError as exc:
        raise ModelUnavailable(
            "torch is not installed. Install the gb10 extra on the box: "
            "pip install -e 'services/agent[gb10]'"
        ) from exc
    if not torch.cuda.is_available():
        raise ModelUnavailable(
            "no CUDA device. This runtime is for the GB10 box; use the mock backend "
            "everywhere else."
        )
    return torch


class SpeechModel:
    """The interface the frame loop needs. Four methods, no more.

    Implementations must be single-threaded and stepped by exactly one caller.
    """

    def step(self, pcm: bytes) -> FrameResult:
        """Consume 80 ms of caller audio, produce one frame of everything."""
        raise NotImplementedError

    def commit_turn(self) -> None:
        """The caller has stopped. Settle and open a response.

        Settling matters: the recognizer needs a short run of silence before the
        turn boundary is safe to declare, and forcing the response open before
        that produces a formally valid, completely empty answer. The runtime pays
        those frames rather than skipping them.
        """
        raise NotImplementedError

    def cancel_response(self, reason: str) -> None:
        """Stop speaking, cleanly.

        Not "discard the audio" — the model's next frame depends on the token it
        emitted this frame, so a response that is simply abandoned leaves it
        believing it is still mid-sentence. It has to be driven to a real end.
        """
        raise NotImplementedError

    def close(self) -> None:
        """Release the model."""


class CudaSpeechModel(SpeechModel):
    """The real thing. Unverified: this has never been run.

    The constructor is cheap and the weights load in `warmup`, because loading is
    minutes and the server needs to bind its socket and report unready first.

    The three seams that have to be wired on the box are marked SEAM below. They
    are the calls into the checkpoint's own module code, which lives with the
    weights rather than in this repo, so they cannot be written blind from here
    without inventing an API that will not match.
    """

    def __init__(self, paths: ModelPaths, codec_cores: Optional[list] = None) -> None:
        self.paths = paths
        self.codec_cores = codec_cores if codec_cores is not None else codec_mod.default_codec_cores()
        self._torch: Any = None
        self._model: Any = None
        self._decoder = codec_mod.PipelinedDecoder(self._decode_codec)
        self._loaded = False

    # --- lifecycle ------------------------------------------------------------

    def warmup(self, instructions: Optional[str] = None) -> None:
        """Load weights and prefill the prompt.

        Prefill happens here rather than on the first turn on purpose. It is the
        single largest one-off cost in a session, and paying it before the client
        is told the session is ready moves it off the candidate's first question,
        where it is the difference between a conversation and a demo that pauses.
        """
        self._torch = require_cuda()
        self.paths.check()
        self._model = self._build()
        if instructions:
            self._prefill(instructions)
        self._loaded = True

    def _build(self) -> Any:
        # SEAM 1: construct the model from the checkpoint's own module code and
        # move it to the device. Quantized backbone, higher-precision synthesis
        # decoder, codec on the pinned CPU worker.
        raise ModelUnavailable(
            "model construction is not wired up yet. This is the one piece that "
            "has to be written against the checkpoint on the box; everything "
            "around it is complete. See docs/11-runtime.md section 10."
        )

    def _prefill(self, instructions: str) -> None:
        # SEAM 2: run the system prompt through the backbone so the session starts
        # with it in state. There is no stateless replay here: the backbone holds
        # recurrent state, so the prompt is prefilled once and then lived with.
        raise ModelUnavailable("prompt prefill is not wired up yet")

    def _decode_codec(self, tokens: Any) -> bytes:
        # SEAM 3: codec tokens to 80 ms of PCM16 at 22.05 kHz, on the pinned CPU
        # worker. Wrapped by PipelinedDecoder so its cost hides under the next step.
        raise ModelUnavailable("codec decode is not wired up yet")

    def close(self) -> None:
        self._model = None
        self._loaded = False

    # --- stepping -------------------------------------------------------------

    def step(self, pcm: bytes) -> FrameResult:
        if not self._loaded:
            raise ModelUnavailable("step before warmup")
        raise ModelUnavailable("model stepping is not wired up yet")

    def commit_turn(self) -> None:
        if not self._loaded:
            raise ModelUnavailable("commit before warmup")
        raise ModelUnavailable("turn commit is not wired up yet")

    def cancel_response(self, reason: str) -> None:
        if not self._loaded:
            return
        raise ModelUnavailable("response cancel is not wired up yet")


class SilenceModel(SpeechModel):
    """A model-shaped object that says nothing. Not a model.

    It exists so the frame loop, the session state machine and the server can be
    run end to end on a laptop: the plumbing is exercised, the lockstep timing is
    real, and the output is silence. It is the runtime's equivalent of the mock
    backend, and like the mock backend it must never be mistaken for a measurement.

    `reply_frames` lets a test make it "speak" for a while so response lifecycle
    and barge-in have something to act on.
    """

    def __init__(self, reply_frames: int = 0, reply_text: str = "") -> None:
        self.reply_frames = reply_frames
        self.reply_text = reply_text
        self._remaining = 0
        self._opened = False
        self._closed = False

    def step(self, pcm: bytes) -> FrameResult:
        if self._closed:
            raise RuntimeError("model is closed")
        control = None
        text = ""
        audible = False
        if self._opened:
            control = "response_open"
            self._opened = False
            text = self.reply_text
        if self._remaining > 0:
            self._remaining -= 1
            audible = True
            if self._remaining == 0:
                control = "response_close"
        return FrameResult(
            text_delta=text,
            audio_pcm=codec_mod.silence(p.OUTPUT_FRAME_BYTES),
            control=control,
            audible=audible,
        )

    def commit_turn(self) -> None:
        self._opened = True
        self._remaining = self.reply_frames

    def cancel_response(self, reason: str) -> None:
        self._remaining = 0
        self._opened = False

    def close(self) -> None:
        self._closed = True


def build_model(paths: ModelPaths, allow_silence: bool = False) -> SpeechModel:
    """Pick a model. Real one if CUDA is there, otherwise fail or fall back.

    The fallback is opt-in rather than automatic. A server that quietly serves
    silence when the GPU is missing is a server that will do exactly that during a
    demo, and nobody will notice until the room is quiet.
    """
    try:
        require_cuda()
    except ModelUnavailable:
        if allow_silence:
            return SilenceModel()
        raise
    return CudaSpeechModel(paths)
