"""The model process: a WebSocket server bound to loopback.

Three moving parts, deliberately kept apart:

- `ServerSession` (session.py) decides the lifecycle. Pure, synchronous, tested.
- `FrameLoop` (loop.py) owns the model on its own thread. Serialized, timed.
- this file moves bytes between them and a socket.

The concurrency rule is the only thing here that is subtle, so it is stated once:
**the session state machine runs on the asyncio thread and nowhere else.** The
frame loop never touches it. It drops `FrameResult`s into a queue and the asyncio
side drains them into the session. Ingestion and consumption are separate tasks,
so a burst of inbound audio cannot delay a turn commit that was sent after it —
that particular starvation is worth designing out up front, because when it
happens it presents as unexplained seconds of latency on one turn in twenty.

Nothing here has been run against a real model.
"""

import argparse
import asyncio
import collections
import logging
import sys
from typing import Any, Deque, Optional

from . import codec as codec_mod
from . import model as model_mod
from . import protocol as p
from .loop import FrameLoop, QueueOverflow
from .session import ServerSession

log = logging.getLogger("zeg.runtime")

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787


def _websockets() -> Any:
    """Import the WebSocket library, lazily and with a useful error."""
    try:
        import websockets  # noqa: WPS433 - deliberate lazy import
    except ImportError as exc:
        raise RuntimeError(
            "the websockets package is required to run the model server. It is not "
            "needed to import zeg or to run the mock backend."
        ) from exc
    return websockets


class RuntimeServer:
    """Serves exactly one conversation at a time.

    Not a limitation to remove later. The model is batch-one and stateful; a second
    session would not be a second conversation, it would be the same one with two
    people talking into it. A second caller gets a "busy" close, which is a true
    answer, and the scaling answer is a second box.
    """

    def __init__(
        self,
        paths: model_mod.ModelPaths,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        allow_silence: bool = False,
        max_session_frames: int = p.MAX_SESSION_FRAMES,
    ) -> None:
        self.paths = paths
        self.host = host
        self.port = port
        self.allow_silence = allow_silence
        self.max_session_frames = max_session_frames
        self.model: Optional[model_mod.SpeechModel] = None
        self._busy = False
        self._sessions = 0

    # --- lifecycle ------------------------------------------------------------

    def load(self) -> None:
        """Load the model before the socket opens.

        Order matters for one boring reason: a client that can connect before the
        weights are resident will connect, and then wait minutes for its first
        frame with no way to tell that from a hang.
        """
        log.info("platform: %s", codec_mod.describe_platform())
        self.model = model_mod.build_model(self.paths, allow_silence=self.allow_silence)
        self.model.load()
        log.info("model loaded: %s", type(self.model).__name__)

    def run(self) -> None:
        self.load()
        asyncio.get_event_loop().run_until_complete(self._serve())

    async def _serve(self) -> None:
        websockets = _websockets()
        # Protocol-level pings are disabled on purpose. A long model step must not
        # be killed by transport keepalive; liveness is an application concern and
        # is carried by session.progress instead.
        async with websockets.serve(
            self._handle, self.host, self.port, ping_interval=None, ping_timeout=None
        ):
            log.info("listening on ws://%s:%d", self.host, self.port)
            await asyncio.Future()

    # --- one connection -------------------------------------------------------

    async def _handle(self, ws: Any) -> None:
        if self._busy:
            log.warning("refusing a second connection; one conversation at a time")
            await ws.close(code=p.CLOSE_BUSY, reason="a conversation is already in progress")
            return
        self._busy = True
        self._sessions += 1
        session = ServerSession(
            "s%d" % self._sessions, max_session_frames=self.max_session_frames
        )
        results: Deque[Any] = collections.deque()
        wake = asyncio.Event()
        aio = asyncio.get_event_loop()

        def on_frame(result: Any) -> None:
            # Model thread. Do nothing here but hand the result across.
            results.append(result)
            aio.call_soon_threadsafe(wake.set)

        loop = FrameLoop(self.model, on_frame)
        loop.start()
        consumer = None
        try:
            await self._send(ws, session.ready())
            consumer = asyncio.ensure_future(self._consume(ws, session, loop, results, wake))
            await self._ingest(ws, session, loop)
        finally:
            if consumer is not None:
                consumer.cancel()
            loop.stop()
            if self.model is not None:
                self.model.close()
            self._busy = False
            log.info("session over: %s", loop.metrics.summary())

    async def _ingest(self, ws: Any, session: ServerSession, loop: FrameLoop) -> None:
        """Read client messages, answer them, and hand work to the loop."""
        aio = asyncio.get_event_loop()
        async for raw in ws:
            try:
                msg = p.parse(raw)
            except p.ProtocolError as exc:
                await self._send(ws, session.wire.error("bad_message", str(exc)))
                continue
            for out in session.on_client(msg):
                if out["type"] == p.CONFIGURED:
                    # The barrier has to mean what it says: the prompt is in model
                    # state before the client is allowed to send audio. Prefill is
                    # seconds of GPU work, so it does not run on the event loop.
                    await aio.run_in_executor(None, self.model.prefill, session.instructions)
                await self._send(ws, out)
            try:
                self._dispatch(session, loop)
            except QueueOverflow as exc:
                for out in session.close("queue_overflow", status="failed"):
                    await self._send(ws, out)
                log.error("%s", exc)
                break
            if session.closed:
                break
        await ws.close(code=p.CLOSE_NORMAL, reason="session closed")

    def _dispatch(self, session: ServerSession, loop: FrameLoop) -> None:
        for action in session.drain_actions():
            if action.kind == "audio":
                loop.submit_audio(action.payload)
            elif action.kind == "commit":
                loop.commit_turn()
            elif action.kind == "cancel":
                loop.cancel(action.payload or "cancel")
            elif action.kind == "say":
                loop.say(action.payload)
            elif action.kind == "steer":
                loop.steer(action.payload)
            elif action.kind == "close":
                loop.stop()

    async def _consume(
        self,
        ws: Any,
        session: ServerSession,
        loop: FrameLoop,
        results: Deque[Any],
        wake: asyncio.Event,
    ) -> None:
        """Drain model frames into the session, on the asyncio thread only."""
        while True:
            await wake.wait()
            wake.clear()
            while results:
                result = results.popleft()
                for out in session.on_frame(result):
                    await self._send(ws, out)
                self._dispatch(session, loop)
            if loop.error is not None:
                for out in session.close("model_error", status="failed"):
                    await self._send(ws, out)
                log.error("model step failed: %s", loop.error)
                return
            if session.closed:
                return

    async def _send(self, ws: Any, msg: Any) -> None:
        await ws.send(p.dumps(msg))


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(prog="zeg-runtime", description="zeg speech runtime")
    parser.add_argument("--weights", default="/opt/zeg/weights", help="checkpoint directory")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--allow-silence",
        action="store_true",
        help="serve silence instead of failing when there is no GPU. Plumbing only.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    server = RuntimeServer(
        model_mod.ModelPaths(args.weights),
        host=args.host,
        port=args.port,
        allow_silence=args.allow_silence,
    )
    try:
        server.run()
    except KeyboardInterrupt:
        return 0
    except model_mod.ModelUnavailable as exc:
        print("cannot start: %s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
