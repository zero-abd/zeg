"""WebRTC transport adapter (aiortc).

Terminates the candidate's browser call and wires it to a CallBridge. Isolated
here so the bridge, framing and playback modules stay import-light and testable
without pulling in aiortc / PyAV; nothing in the test path imports this file.

Resampling is asymmetric on purpose (see services/agent/zeg/audio.py). The
inbound, recognition-bound leg uses PyAV's proper resampler, because upsampling
without an anti-alias filter measurably degrades recognition and a transcription
gap becomes a scoring gap. The outbound leg is playback only, so the cheap
linear resampler in zeg.audio is good enough there.
"""

import asyncio
import fractions
import logging
import time

import av
from aiortc import MediaStreamTrack
from aiortc.mediastreams import MediaStreamError

from zeg.audio import AudioFrame, resample_linear
from zeg.config import INPUT_SAMPLE_RATE

from .framing import FrameChunker

log = logging.getLogger("gateway.webrtc")

#: Browsers negotiate Opus at 48 kHz; playing back at that rate avoids a second
#: resample inside the encoder.
PLAYBACK_RATE = 48_000
PLAYBACK_FRAME_MS = 20
PLAYBACK_SAMPLES = PLAYBACK_RATE * PLAYBACK_FRAME_MS // 1000  # 960


class AgentPlaybackTrack(MediaStreamTrack):
    """Streams the agent's voice to the candidate at a steady 20 ms cadence.

    Serves silence when the playback buffer is empty. `recv` paces itself to the
    wall clock so the agent is not fast-forwarded when the transport is idle.
    """

    kind = "audio"

    def __init__(self, playback) -> None:
        super().__init__()
        self._playback = playback
        self._samples = 0
        self._start = None

    async def recv(self) -> "av.AudioFrame":
        if self._start is None:
            self._start = time.monotonic()
        target = self._start + (self._samples + PLAYBACK_SAMPLES) / PLAYBACK_RATE
        delay = target - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)

        pcm = self._playback.take(PLAYBACK_SAMPLES)  # silence-padded to a full frame
        frame = av.AudioFrame(format="s16", layout="mono", samples=PLAYBACK_SAMPLES)
        frame.planes[0].update(pcm)
        frame.sample_rate = PLAYBACK_RATE
        frame.pts = self._samples
        frame.time_base = fractions.Fraction(1, PLAYBACK_RATE)
        self._samples += PLAYBACK_SAMPLES
        return frame


def enqueue_agent_audio(playback, frame: AudioFrame) -> None:
    """Upsample one 22.05 kHz agent frame to 48 kHz and queue it for playback."""
    playback.enqueue(resample_linear(frame, PLAYBACK_RATE).pcm)


async def consume_audio(track, bridge) -> None:
    """Pull inbound mic frames, resample to 16 kHz mono, feed the bridge."""
    resampler = av.AudioResampler(format="s16", layout="mono", rate=INPUT_SAMPLE_RATE)
    chunker = FrameChunker(sample_rate=INPUT_SAMPLE_RATE)
    while True:
        try:
            frame = await track.recv()
        except MediaStreamError:
            break
        for resampled in _as_list(resampler.resample(frame)):
            pcm = bytes(resampled.planes[0])[: resampled.samples * 2]
            for af in chunker.push(pcm):
                bridge.feed(af)
    log.info("inbound audio track ended")


async def consume_video(track, video_sink=None) -> None:
    """Drain the optional video track.

    Video is a stretch (README: first thing to cut) and off the audio critical
    path, but we must keep draining the track or it stalls. `video_sink` is the
    Track 4 seam: hand each frame to MediaPipe gaze estimation here. For now we
    only count frames.
    """
    count = 0
    while True:
        try:
            frame = await track.recv()
        except MediaStreamError:
            break
        count += 1
        if video_sink is not None:
            video_sink(frame, count)
    log.info("inbound video track ended after %d frames", count)


def _as_list(x):
    """PyAV's resample() returns a list on new versions, one frame on old."""
    if x is None:
        return []
    return x if isinstance(x, list) else [x]
