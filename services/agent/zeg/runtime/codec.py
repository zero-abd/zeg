"""Audio codec decode, off the critical path.

The model's synthesis stage emits codec tokens, not waveform. Turning those into
PCM is the last stage of every frame, and on this box it is the stage most likely
to be in the wrong place: the codec decoder is small, its convolutions are
grouped and depthwise, and on the box's ARM64 build those kernels fall off the
fast path badly enough that running them on the GPU is slower than running them
on a pinned CPU core.

Two mechanisms here, both independent of which decoder is actually used:

**Core pinning.** The box has performance and efficiency cores. A realtime decode
scheduled onto an efficiency core misses the frame budget on its own. Pinning is
a no-op on platforms without affinity control, which is every developer laptop.

**One-frame pipelining.** The call for frame F submits F and returns F-1. That
hides the entire decode behind the next model step at the cost of exactly one
frame of latency, 80 ms, paid once at the start of a response rather than per
frame. This is the whole trick and it is why the decode stage does not need to be
fast, only bounded.

The pipelining is pure and tested. The decoder it wraps is not: that needs the
box.
"""

import os
import sys
from typing import Callable, List, Optional, Sequence


def pin_to_cores(cores: Sequence[int], thread_id: int = 0) -> bool:
    """Pin `thread_id` to `cores`, the current process by default. Returns whether it
    took effect.

    A thread id rather than only the process, because the decode wants its own cores and
    the model step must not be pinned with it. On Linux `threading.get_native_id()` is
    what to pass; 0 means this process, which is what a standalone codec worker wants.

    Fails soft. A missing affinity API is a developer laptop, not a broken box,
    and refusing to start there would make the runtime undevelopable. On the box
    the caller should check the return value and complain loudly, because an
    unpinned codec worker is a frame-budget problem that looks like a model
    problem.
    """
    setter = getattr(os, "sched_setaffinity", None)
    if setter is None:  # macOS, Windows
        return False
    try:
        setter(thread_id, set(cores))
    except OSError:
        return False
    return True


def default_codec_cores() -> List[int]:
    """Cores to give the codec worker.

    Two performance cores, chosen away from core 0 because that is where the
    kernel puts interrupt work. The real numbers belong in deployment config once
    somebody has looked at the box's topology; this is a starting point, not a
    measurement.
    """
    count = os.cpu_count() or 4
    if count >= 8:
        return [5, 6]
    return [max(0, count - 2), max(0, count - 1)]


class PipelinedDecoder:
    """Runs a decoder one frame behind, so its cost hides under the next step.

    `submit(tokens)` returns the PCM for the *previous* submission, or None on the
    first call. `flush()` drains the last one. The queue never grows: exactly one
    frame is ever in flight, because a decoder that can fall behind is a decoder
    that turns into unbounded queue debt three minutes into a call.
    """

    def __init__(self, decode: Callable[[object], bytes]) -> None:
        self._decode = decode
        self._pending: Optional[object] = None

    def submit(self, tokens: object) -> Optional[bytes]:
        # Decode only what is actually in flight. A "started" flag used to decide this, and
        # it stayed set after flush() emptied the pipeline, so the first frame of the next
        # response asked the codec to decode None: a strict codec raised, and the session
        # died at the start of the agent's second reply.
        previous, self._pending = self._pending, tokens
        if previous is None:
            return None
        return self._decode(previous)

    def flush(self) -> Optional[bytes]:
        """Decode whatever is still in flight. Call once, at the end of a response."""
        if self._pending is None:
            return None
        tokens, self._pending = self._pending, None
        return self._decode(tokens)

    @property
    def in_flight(self) -> bool:
        return self._pending is not None


def silence(n_bytes: int) -> bytes:
    """A frame of digital silence. The decoder's fallback, and the loop's filler."""
    return b"\x00" * n_bytes


def describe_platform() -> str:
    """One line for the startup log. Cheap, and it answers the first question."""
    return "%s %s, %d cpus, affinity=%s" % (
        sys.platform,
        os.uname().machine if hasattr(os, "uname") else "?",
        os.cpu_count() or 0,
        hasattr(os, "sched_setaffinity"),
    )
