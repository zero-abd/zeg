"""aiohttp signaling server.

Serves the candidate page and answers one WebRTC offer at a time. The box runs a
single conversation (docs/11 §9, GB10Backend refuses a second session), so a
second offer is refused with 409 rather than quietly starting a call the model
cannot serve.

Each call gets a fresh backend session, a CallBridge, and a playback track. When
the peer connection drops, the session is closed and the transcript is printed
for the scoring step to pick up.

When the candidate sends their camera and the vision module is built (`make vision`),
the video track feeds a GazeReview (video_review.py). At hangup its flags are logged as
the report's "Video review" section and, with --review-dir, saved as JSON beside the
call for the scoring step. They are moments for a human to watch, never a score input.
"""

import argparse
import asyncio
import logging
import os
import time

from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription

from zeg.backends import build_backend
from zeg.config import AudioConfig, BackendConfig
from zeg.prompts import GREETING, SYSTEM_PROMPT
from zeg.video_review import flags_from, render_video_review

from .bridge import CallBridge
from .playback import PlaybackBuffer
from .video_review import GazeReview, save_flags
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

    def __init__(
        self, backend_kind: str = "mock", video_review: bool = True, review_dir: str = ""
    ) -> None:
        self._backend = build_backend(BackendConfig(kind=backend_kind, audio=AudioConfig()))
        self._backend.warmup()
        self._pc = None
        self._bridge = None
        self._review = None
        self._video_review = video_review and GazeReview.available()
        self._review_dir = review_dir
        if video_review and not self._video_review:
            log.info("video review off: zeg_gaze is not built (make vision)")

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
        call_started = time.monotonic()

        @pc.on("track")
        def on_track(track):  # noqa: WPS430
            log.info("candidate %s track", track.kind)
            if track.kind == "audio":
                asyncio.ensure_future(consume_audio(track, bridge))
            elif track.kind == "video":
                sink = None
                if self._video_review and self._review is None:
                    # Flag times on the call clock, from when the offer was answered.
                    self._review = GazeReview(started_at=call_started)
                    sink = self._review.sink
                asyncio.ensure_future(consume_video(track, video_sink=sink))

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
            if self._review is not None:
                self._review.finish()
                self._review = None
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
        if self._review is not None:
            review, self._review = self._review, None
            flags = await asyncio.get_event_loop().run_in_executor(None, review.finish)
            self._report_video(flags)
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

    def _report_video(self, flags) -> None:
        for line in render_video_review(flags_from(flags)):
            log.info("%s", line)
        if self._review_dir:
            stamp = time.strftime("%Y%m%d-%H%M%S")
            path = save_flags(flags, os.path.join(self._review_dir, stamp))
            log.info("video flags saved to %s", path)

    async def index(self, request: web.Request) -> web.Response:
        return web.FileResponse(os.path.join(WEB_DIR, "interview.html"))

    async def healthz(self, request: web.Request) -> web.Response:
        return web.json_response(
            {"ok": True, "in_call": self._pc is not None, "backend": self._backend.name}
        )


def build_app(
    backend_kind: str = "mock", video_review: bool = True, review_dir: str = ""
) -> web.Application:
    gw = Gateway(backend_kind=backend_kind, video_review=video_review, review_dir=review_dir)
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
    ap.add_argument("--no-video-review", action="store_true",
                    help="do not analyse the candidate's camera even when zeg_gaze is built")
    ap.add_argument("--review-dir", default="",
                    help="save each call's video flags as JSON under this directory")
    args = ap.parse_args(argv)
    log.info("gateway on http://%s:%d  (backend=%s)", args.host, args.port, args.backend)
    web.run_app(
        build_app(
            backend_kind=args.backend,
            video_review=not args.no_video_review,
            review_dir=args.review_dir,
        ),
        host=args.host,
        port=args.port,
    )


if __name__ == "__main__":
    run()
