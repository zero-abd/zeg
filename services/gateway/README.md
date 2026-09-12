# services/gateway — call joining and A/V ingestion

**Owner: Eunice (Track 2)**

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
