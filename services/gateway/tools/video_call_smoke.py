"""A real WebRTC call into the gateway, with a video file as the candidate's camera.

    PYTHONPATH=services/gateway:services/agent:services/vision/build \\
        .venv/bin/python services/gateway/tools/video_call_smoke.py clip.avi [--seconds 40]

Starts the gateway in this process (mock backend), then plays `clip` as the camera and
silence as the microphone through an aiortc peer connection over loopback, exactly the
media path a browser uses: SDP offer/answer over HTTP, VP8 encode and decode, RTP. At
the end it hangs up, and the gateway logs the transcript and the "Video review"
section built from the flags the live detector produced. Needs `make gateway-setup`
and `make vision`.
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import tempfile

from aiohttp import ClientSession, web
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaPlayer
from aiortc.mediastreams import AudioStreamTrack

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gateway.server import build_app  # noqa: E402


async def call(clip: str, seconds: float, port: int, review_dir: str) -> None:
    app = build_app(backend_kind="mock", review_dir=review_dir)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", port).start()

    pc = RTCPeerConnection()
    player = MediaPlayer(clip)
    pc.addTrack(AudioStreamTrack())  # silence: the mock agent just keeps talking
    pc.addTrack(player.video)
    await pc.setLocalDescription(await pc.createOffer())
    while pc.iceGatheringState != "complete":
        await asyncio.sleep(0.05)
    async with ClientSession() as http:
        async with http.post(
            "http://127.0.0.1:%d/offer" % port,
            json={"sdp": pc.localDescription.sdp, "type": pc.localDescription.type},
        ) as resp:
            answer = await resp.json()
    await pc.setRemoteDescription(RTCSessionDescription(**answer))
    print("call up; streaming %s for %.0f s" % (clip, seconds), flush=True)
    await asyncio.sleep(seconds)
    await pc.close()
    await asyncio.sleep(3.0)  # let the gateway see the hangup and finish the review
    await runner.cleanup()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("clip")
    ap.add_argument("--seconds", type=float, default=40.0)
    ap.add_argument("--port", type=int, default=8791)
    ap.add_argument("--review-dir", default="")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    for noisy in ("aiohttp.access", "aioice", "aiortc"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    review_dir = args.review_dir or tempfile.mkdtemp(prefix="zeg-review-")
    asyncio.run(call(args.clip, args.seconds, args.port, review_dir))
    for root, _, files in os.walk(review_dir):
        for name in files:
            path = os.path.join(root, name)
            print("saved %s:" % path)
            print(json.dumps(json.load(open(path)), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
