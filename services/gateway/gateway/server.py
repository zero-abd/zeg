"""aiohttp signaling server.

Serves the candidate page and answers one WebRTC offer at a time. The box runs a
single conversation (docs/11 §9, GB10Backend refuses a second session), so a
second offer is refused with 409 rather than quietly starting a call the model
cannot serve.

Each call gets a fresh backend session, a CallBridge, and a playback track. When
the peer connection drops, the session is closed and the transcript is printed
for the scoring step to pick up.
"""

import argparse
import asyncio
import logging
import os

from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription

from zeg.backends import build_backend
from zeg.config import AudioConfig, BackendConfig
from zeg.prompts import GREETING, SYSTEM_PROMPT

from .bridge import CallBridge
from .playback import PlaybackBuffer
from .webrtc import (
    PLAYBACK_RATE,
    AgentPlaybackTrack,
    consume_audio,
    consume_video,
    enqueue_agent_audio,
)

log = logging.getLogger("gateway.server")

WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")


class Gateway:
    """Holds the single loaded backend and the single active call."""

    def __init__(self, backend_kind: str = "mock") -> None:
        self._backend = build_backend(BackendConfig(kind=backend_kind, audio=AudioConfig()))
        self._backend.warmup()
        self._pc = None
        self._bridge = None

    async def offer(self, request: web.Request) -> web.Response:
        if self._pc is not None:
            return web.json_response({"error": "a call is already in progress"}, status=409)

        params = await request.json()
        if not params.get("sdp") or params.get("type") != "offer":
            return web.json_response({"error": "expected an SDP offer"}, status=400)

        pc = RTCPeerConnection()
        playback = PlaybackBuffer(sample_rate=PLAYBACK_RATE)
        session = self._backend.start_session(SYSTEM_PROMPT, greeting=GREETING)
        bridge = CallBridge(
            session,
            on_agent_audio=lambda frame: enqueue_agent_audio(playback, frame),
            on_interrupt=playback.flush,
        )
        pc.addTrack(AgentPlaybackTrack(playback))

        @pc.on("track")
        def on_track(track):  # noqa: WPS430
            log.info("candidate %s track", track.kind)
            if track.kind == "audio":
                asyncio.ensure_future(consume_audio(track, bridge))
            elif track.kind == "video":
                asyncio.ensure_future(consume_video(track))

        @pc.on("connectionstatechange")
        async def on_state():  # noqa: WPS430
            log.info("connection: %s", pc.connectionState)
            if pc.connectionState in ("failed", "closed", "disconnected"):
                await self._teardown()

        try:
            await pc.setRemoteDescription(RTCSessionDescription(sdp=params["sdp"], type="offer"))
            await pc.setLocalDescription(await pc.createAnswer())
        except Exception as exc:  # malformed SDP must not wedge the single call slot
            await pc.close()
            session.close()
            log.warning("offer rejected: %r", exc)
            return web.json_response({"error": "invalid offer: %s" % exc}, status=400)

        # Reserve the single call slot only once negotiation has actually succeeded.
        self._pc = pc
        self._bridge = bridge
        return web.json_response(
            {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
        )

    async def _teardown(self) -> None:
        if self._bridge is not None:
            self._report(self._bridge)
            self._bridge.close()
            self._bridge = None
        if self._pc is not None:
            pc, self._pc = self._pc, None
            await pc.close()

    def _report(self, bridge: CallBridge) -> None:
        log.info(
            "---- transcript: %d turns, %d interruptions, %.1fs agent speech ----",
            len(bridge.transcript),
            bridge.interruptions,
            bridge.agent_audio_s,
        )
        for speaker, text in bridge.transcript:
            log.info("  %-6s %s", speaker, text)
        if bridge.error:
            log.warning("backend error: %s", bridge.error)

    async def index(self, request: web.Request) -> web.Response:
        return web.FileResponse(os.path.join(WEB_DIR, "interview.html"))

    async def healthz(self, request: web.Request) -> web.Response:
        return web.json_response(
            {"ok": True, "in_call": self._pc is not None, "backend": self._backend.name}
        )


def build_app(backend_kind: str = "mock") -> web.Application:
    gw = Gateway(backend_kind=backend_kind)
    app = web.Application()
    app.router.add_get("/", gw.index)
    app.router.add_get("/healthz", gw.healthz)
    app.router.add_post("/offer", gw.offer)
    app["gateway"] = gw
    return app


def run(argv=None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(prog="zeg-gateway")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--backend", default="mock", choices=["mock", "tts", "gb10"])
    args = ap.parse_args(argv)
    log.info("gateway on http://%s:%d  (backend=%s)", args.host, args.port, args.backend)
    web.run_app(build_app(backend_kind=args.backend), host=args.host, port=args.port)


if __name__ == "__main__":
    run()
