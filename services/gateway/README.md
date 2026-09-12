# services/gateway — call joining and A/V ingestion

**Owner: Hyunsuh (Track 2)**

Goal: get a candidate's audio into the box and the agent's audio back out, over a
link the candidate can open in a browser.

## Recommended approach

A browser client over WebRTC, not Google Meet. Meet has no supported way for a bot to
reach raw call audio; the realistic build is headless Chrome with virtual audio
devices, which is a day of work that fails in ways that are hard to debug under time
pressure. A plain WebRTC page is the same audio path, a few hours, and demos
identically.

Attempt Meet only once the browser path works end to end. See `plan.md` section 2.

## Start here

1. `../agent/zeg/audio.py`. Defines the frame format everything speaks: mono PCM16,
   20 ms frames. `resample_linear` is there, but read its docstring before using it on
   the real path.
2. `../agent/zeg/config.py`. The rates you have to hit. The model consumes 16 kHz and
   emits 22.05 kHz, while browsers and phones will hand you something else. A resample
   sits on both ends.
3. `../agent/zeg/conversation.py`. Shows how frames flow in and events come out. Your
   transport replaces the simulated caller in that file.

## What you are building toward

Something that pushes `AudioFrame`s into a `VoiceSession` and plays back the
`AgentAudio` frames it emits. The session interface is in
`../agent/zeg/backends/base.py`.

The one behaviour that must be right is **playback cancellation**. When
`AgentInterrupted` arrives, everything already queued for playback has to be dropped
immediately, or the candidate hears the agent talking over them. This is the single
most visible quality signal in a voice agent.

## Stretch: eye tracking

MediaPipe, flag gaze beyond 30 to 45 degrees for more than 5 seconds, save the clip
for recruiter review. Needs the video channel, which the audio path does not. First
thing to cut if time runs short.

## Implementation

Built against the plan above. Audio-first; video is an optional WebRTC track with a
Track-4 seam, nothing more.

```
gateway/
  framing.py    rechunk a resampled PCM stream into exact 20 ms AudioFrames
  playback.py   playback FIFO + the barge-in flush()
  bridge.py     transport-agnostic core: caller frame in -> VoiceSession -> events out
  webrtc.py     aiortc adapter: resample 48k<->16k/22.05k, the outbound audio track
  server.py     aiohttp signaling, one call at a time, prints the transcript on hangup
web/interview.html   candidate page: getUserMedia -> RTCPeerConnection -> /offer
tools/meet_provision.py   stretch-only Google Meet link (see its header)
```

The split that matters: `bridge.py` is pure and imports no transport, so the barge-in
behaviour is unit-tested against the mock backend with no browser and no aiortc. The
WebRTC adapter is the only file that touches PyAV. Resampling is asymmetric on purpose
(see `../agent/zeg/audio.py`): the inbound recognition leg uses PyAV's proper
resampler, the outbound playback leg uses the cheap linear one.

```bash
make gateway-test               # bridge / framing / playback, no transport deps
make gateway-setup              # aiortc + aiohttp into .venv (heavy: PyAV)
make gateway                    # http://localhost:8080  (BACKEND=mock by default)
```

Open the page, click Join: the mock backend greets you with the disclosure + consent
line and streams a 220 Hz tone as its "voice". Swap to the real model with
`make gateway BACKEND=gb10` once `services/agent/zeg/backends/gb10.py` exists.

Remote candidates need HTTPS (mic is blocked on insecure origins off localhost):

```bash
cloudflared tunnel --url http://localhost:8080     # or: ngrok http 8080
```

**Not yet done / handoffs:** the WebRTC media path is validated by unit tests and a
clean server boot, but the browser SDP handshake needs a real browser to exercise
end to end (couldn't be done headless here). The gaze `video_sink` in `webrtc.py` is
a stub for Track 4. Scoring picks up `bridge.transcript` after hangup.
