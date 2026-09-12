"""The frame loop.

One thread, one model, one frame every 80 ms. Everything the model does goes
through here and nothing else is allowed to touch it, because the model's state is
recurrent: two threads stepping it does not interleave two conversations, it
corrupts one.

Strict serialization is the feature, not a limitation to engineer around later.

The loop's other job is to make the frame budget visible. A model step that takes
95 ms does not lose the extra 15 ms — it becomes queue debt that delays every
later frame in the call, and by minute ten the agent is answering the question
before last. So every step is timed against the budget and over-budget frames are
counted explicitly. A counter that says "41 frames were late" is worth more than a
mean that says everything is fine.
"""

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Optional, Tuple

from . import protocol as p
from .session import FrameResult

#: Work items waiting for the model. At 80 ms a frame, 64 is five seconds of
#: backlog, which is already a failed call — the bound exists so the failure is
#: reported rather than silently absorbed into growing latency.
MAX_QUEUE = 64


@dataclass
class FrameMetrics:
    """Per-session frame accounting. Cheap enough to keep always on."""

    frames: int = 0
    over_budget: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0
    dropped: int = 0

    @property
    def mean_ms(self) -> float:
        return self.total_ms / self.frames if self.frames else 0.0

    def observe(self, elapsed_ms: float, budget_ms: float) -> bool:
        self.frames += 1
        self.total_ms += elapsed_ms
        self.max_ms = max(self.max_ms, elapsed_ms)
        late = elapsed_ms > budget_ms
        if late:
            self.over_budget += 1
        return late

    def summary(self) -> str:
        return "frames=%d mean=%.1fms max=%.1fms over_budget=%d dropped=%d" % (
            self.frames,
            self.mean_ms,
            self.max_ms,
            self.over_budget,
            self.dropped,
        )


class QueueOverflow(RuntimeError):
    """The model fell far enough behind that the backlog is unrecoverable.

    Fatal by design. The alternative is dropping caller audio, and audio dropped
    out of the middle of an utterance does not produce a slightly worse transcript,
    it produces a confident wrong one.
    """


class FrameLoop:
    """Serializes model work and reports what it cost.

    Drive it either way: `start()` runs it on its own thread, or call
    `run_pending()` from a test and step it by hand. The second mode is why the
    loop keeps no timing state of its own beyond the metrics — a deterministic
    test must be able to drive a whole call without sleeping.
    """

    def __init__(
        self,
        model: Any,
        on_frame: Callable[[FrameResult], None],
        budget_ms: float = float(p.FRAME_MS),
        max_queue: int = MAX_QUEUE,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.model = model
        self.on_frame = on_frame
        self.budget_ms = budget_ms
        self.max_queue = max_queue
        self.clock = clock
        self.metrics = FrameMetrics()

        self._queue: Deque[Tuple[str, Any]] = deque()
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self.error: Optional[BaseException] = None

    # --- submitting work ------------------------------------------------------

    def submit_audio(self, pcm: bytes) -> None:
        self._put(("audio", pcm))

    def commit_turn(self) -> None:
        """Caller stopped talking. Ordered behind the audio already queued.

        Order is the whole point. A commit that overtakes unconsumed audio ends the
        turn before the model has heard the end of it, which is the single most
        expensive ordering bug available in this design.
        """
        self._put(("commit", None))

    def cancel(self, reason: str) -> None:
        """Barge-in. Jumps the queue, because a cancel that waits is not a cancel.

        The audio behind it is still delivered afterwards; only the ordering of the
        control signal changes. The model needs to stop speaking now, and it needs
        to hear everything the caller said either way.
        """
        with self._lock:
            self._queue.appendleft(("cancel", reason))
        self._wake.set()

    def _put(self, item: Tuple[str, Any]) -> None:
        with self._lock:
            if len(self._queue) >= self.max_queue:
                self.metrics.dropped += 1
                raise QueueOverflow(
                    "model is %d frames behind; the session cannot recover" % len(self._queue)
                )
            self._queue.append(item)
        self._wake.set()

    @property
    def depth(self) -> int:
        with self._lock:
            return len(self._queue)

    # --- doing work -----------------------------------------------------------

    def run_pending(self, limit: int = 0) -> int:
        """Process queued work now. Returns how many items were handled."""
        handled = 0
        while True:
            if limit and handled >= limit:
                return handled
            with self._lock:
                if not self._queue:
                    return handled
                kind, payload = self._queue.popleft()
            self._handle(kind, payload)
            handled += 1

    def _handle(self, kind: str, payload: Any) -> None:
        if kind == "cancel":
            self.model.cancel_response(payload)
            return
        if kind == "commit":
            self.model.commit_turn()
            return

        started = self.clock()
        result = self.model.step(payload)
        elapsed_ms = (self.clock() - started) * 1000.0
        result.over_budget = self.metrics.observe(elapsed_ms, self.budget_ms)
        self.on_frame(result)

    # --- thread mode ----------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, name="zeg-frame-loop", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while self._running:
            self._wake.wait(timeout=0.1)
            self._wake.clear()
            try:
                self.run_pending()
            except BaseException as exc:  # noqa: B902 - the loop owns the model
                # Stop rather than limp. A model that raised mid-step has unknown
                # internal state and the next frame would be built on it.
                self.error = exc
                self._running = False
                return

    def stop(self) -> None:
        self._running = False
        self._wake.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=2.0)
