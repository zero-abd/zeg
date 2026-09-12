# The serving runtime

How `zeg` actually talks to the speech model on the GB10 box: the process split, the
wire protocol between them, the frame clock, and the failure behaviour.

This document describes what `services/agent/zeg/backends/gb10.py` and
`services/agent/zeg/runtime/` do. The contract they honour upward is
`services/agent/zeg/backends/base.py`, which does not change. The mock backend in the
same package stays the reference for *behaviour*: full duplex, partial then final
transcripts, barge-in, streamed output frames. Anything the real runtime does that the
mock does not do is a bug in one of them.

## 1. Two processes, one box

```
media path ──► zeg call process                ──► model process
 (WebRTC)       GB10Backend / GB10Session           zeg.runtime
                                                    │
                ├─ voice gate, turn barriers        ├─ speech encoder
                ├─ playout queue, barge-in          ├─ quantized backbone
                ├─ frame-clock watchdog             ├─ synthesis decoder
                ├─ session frame budget             ├─ audio codec (CPU worker)
                └─ interview engine above           └─ frame loop, 80 ms budget
                          │                                   │
                          └────── loopback WebSocket ─────────┘
                                  127.0.0.1 only
```

They are separate processes for three reasons, in order of how much they cost us if we
get them wrong:

1. **Model load is minutes; the call process must be restartable in seconds.** The
   interview prompt, the plan and the rubric are the things we iterate on during a
   hackathon. Restarting the call process must not unload 12 GiB of weights.
2. **The model process is stateful and single-tenant.** It holds recurrent state plus a
   key/value cache for one conversation. A crash in our interview logic must not be able
   to corrupt it, and our logic must not be able to reach into it.
3. **Blast radius.** The model process binds loopback only. Nothing candidate-facing
   speaks to it directly.

They are on one box because that is the product. No audio leaves the device.

## 2. The 80 ms frame

The model is a lockstep machine. One step consumes 80 ms of caller audio and produces
one agent text token and 80 ms of agent audio, whether or not the agent is speaking.
Everything in the runtime is counted in those frames rather than in seconds, because
the frame is the only clock both processes agree on.

Three rates, and they line up exactly:

| Rate | Value | Why it matters |
| --- | --- | --- |
| Model frame | 80 ms | One model step. The budget. |
| Transport frame | 20 ms | RTP convention, what `AudioConfig.frame_ms` says. |
| Output sample rate | 22.05 kHz | 1764 samples per model frame. |

A model frame is exactly four transport frames on the way in (4 × 320 samples at
16 kHz = 1280) and exactly four on the way out (4 × 441 samples at 22.05 kHz = 1764).
No remainder, so nothing has to be repacketized and no drift accumulates over a
15-minute call. This is worth stating because it is the reason we can keep 20 ms
framing above the backend and 80 ms framing below it without a resampling buffer in
between.

The consequence to internalize: **the model cannot skip frames.** If a step takes 95 ms,
the 15 ms does not vanish, it becomes queue debt that delays every later frame in the
call. So the runtime measures per-frame cost and counts over-budget frames explicitly
rather than letting a queue absorb them silently. A visible counter is worth more than a
lower mean.

## 3. Who decides when a turn ends

**The call process owns turn boundaries. The model process owns continuous model
state.** This is the single most important division in the design and everything else
follows from it.

The model has its own endpointer and can decide for itself when the caller has stopped
talking. We do not use it. Its threshold is tuned for natural conversational pauses of
around 1.6 seconds, which in an interview is the exact moment a candidate is thinking
about how to describe a race condition, and interrupting there is the worst thing a
screening agent can do. We want that threshold under our control, because endpointing
policy is an interview design decision, not a model property.

So the call process runs a cheap voice gate and sends explicit, correlated barriers:

```
input.turn_start   (turn 3)     caller started speaking
input.audio        × n          80 ms of PCM16 at 16 kHz, base64 in JSON
input.turn_commit  (turn 3)     caller stopped; produce exactly one reply
```

Rules that make this safe, each of which exists because of a specific way it can go
wrong:

- **The commit is authoritative even if the model recognized nothing.** A commit
  requests exactly one turn transition. If the caller coughed, the model answers the
  silence; it does not sit there waiting for its own endpointer to agree.
- **Barriers are acknowledged and correlated by turn number.** Acks are idempotent, so
  a retry is harmless. A mismatched or overlapping turn is fatal, because a half-sent
  audio turn cannot be rolled back — the model has already consumed those frames into
  its recurrent state, and there is no undo.
- **Audio may arrive before the barrier.** The voice gate fires a frame or two after
  speech actually begins, so the call process keeps a small pre-roll and sends it with
  the turn start. Without this the model loses the first syllable, which it then
  hallucinates back, badly.
- **A new turn start cancels an open response first.** One response per turn, always
  terminated, never abandoned.

The model process still runs its own recognizer, and its transcript is what we record.
We are choosing where the boundary is, not doing the recognition ourselves.

## 4. Barge-in

When the caller talks over the agent, two things must happen, and they happen in
different places on purpose.

**Locally, immediately.** The call process drops its playout queue and emits
`AgentInterrupted` the moment the voice gate trips. It does not wait for the model to
agree. A round trip plus one model step is at least another 80 ms of the agent talking
over a candidate, and the whole call is judged on this behaviour.

**Remotely, correctly.** The call process also sends `response.cancel`. The model needs
to close its response properly — its next frame depends on the token it emitted last
frame, so a response that is simply abandoned leaves the model believing it is still
mid-sentence. The server drives the response to a real terminal and confirms with
`response.cancelled`.

The local event is the user-visible one; the remote one keeps the model coherent. The
call process reconciles them by ignoring any audio frames that arrive for a response it
has already cancelled.

## 5. Wire protocol

JSON text frames on a loopback WebSocket, one session per connection. Audio is base64
inside the JSON rather than a binary frame, which costs about 33% on a loopback socket
that has bandwidth to spare and buys a single ordered stream of events with no
correlation problem between two framings. Ordering is the thing that is hard to debug
here; bytes are not.

Every message has a `type` and an `event_id`. Turn-scoped and response-scoped messages
carry `turn` and `response_id`.

**Client to server**

| Type | Meaning |
| --- | --- |
| `session.configure` | Protocol version, system instructions, greeting, limits. Sent once. |
| `input.turn_start` | Opens turn *n*. Carries any pre-roll frame count. |
| `input.audio` | One 80 ms PCM16 mono 16 kHz frame, base64. |
| `input.turn_commit` | Closes turn *n*. Requests exactly one response. |
| `response.cancel` | Barge-in. Drive the open response to a terminal. |
| `session.stop` | Graceful close. |

**Server to client**

| Type | Meaning |
| --- | --- |
| `session.ready` | Protocol name and version, limits, capabilities. |
| `session.configured` | The model-ready barrier. Prompt is prefilled. |
| `input.turn_started` / `input.turn_committed` | Correlated barrier acks. |
| `transcript.delta` / `transcript.final` | What the caller said. Partial, then stable. |
| `response.started` | A response opened for a turn. |
| `response.text` | Agent text, as it is spoken. |
| `response.audio` | One 80 ms PCM16 mono 22.05 kHz frame, base64. |
| `response.cancelled` / `response.done` | Response terminal, always exactly one. |
| `session.progress` | Frames consumed, frames remaining, over-budget count. |
| `error` | `code`, `message`, `fatal`. |
| `session.closed` | Permanent. Reason. |

Two details that look fussy and are not:

**`session.configured` is a barrier, not an acknowledgement.** It is sent only after the
system prompt has been prefilled into the model. The call process does not send audio
before it. Audio captured during startup is *discarded*, never buffered and replayed —
replaying two seconds of stale audio into a model that is now listening is worse than
losing it, because the candidate has moved on and the model answers a question nobody
is still asking.

**Transport keepalive is disabled; liveness is an application timer.** A slow model step
must not be killed by a ping timeout. What we actually care about is whether the model
is producing frames, and that is what `session.progress` reports.

## 6. The watchdog, and why it counts frames

`docs/02-hardware-and-models.md` states the requirement plainly: the candidate is never
left on a silent line. The runtime has to end a wedged call cleanly rather than hang.

The watchdog is driven by **caller frames pushed, not by wall clock.** This is a
deliberate choice and the reasoning is worth keeping:

- Caller audio arrives in real time by definition. It comes off the media path at
  20 ms per 20 ms. Counting it is counting real elapsed call time.
- The failure we are guarding against is the model process wedging while the media path
  is healthy. In that failure the caller keeps talking, so frames keep arriving, so a
  frame-driven watchdog fires.
- A wall clock would also fire during the replay harness, where a 15-minute call runs in
  under a second of wall time. The conversation harness in `conversation.py` is
  explicitly virtual-clock; a wall-clock watchdog would be untestable there and would be
  the one piece of failure handling we never exercise.

If the media path itself dies, `push_audio` stops being called, and the layer above
notices — that is not the backend's problem to detect.

Default: if no event of any kind arrives from the model process for 200 caller frames
(4 seconds) while we are expecting output, the session emits a fatal `BackendError` and
closes. The interview engine's job at that point is to apologize and hang up, which is
option 1 from the failure list in `docs/02`.

The model process runs its own watchdogs on the other side, on things the client cannot
see: a response that opened and then produced neither text nor audible audio for 30
frames, a response still open after a wall-clock deadline, output that has been
inaudible for 12 frames after something audible was heard. All of them resolve to
"close this response cleanly", never to "invent something to say".

## 7. The session frame budget

The model's serving stack caps a session at 12,000 frames. At 80 ms that is exactly 16
minutes, and it is a hard limit, not a soft one — past it the session is closed.

The call process counts its own frames and treats the cap as ours to respect, not as
something to discover:

| Budget | Frames | Wall | What happens |
| --- | ---: | --- | --- |
| Interview wrap-up | 10,125 | 13:30 | `CallConfig.wrap_up_at_s`. The engine starts closing. |
| Hard wall clock | 11,250 | 15:00 | `CallConfig.max_duration_s`. The engine ends the call. |
| Session frame cap | 12,000 | 16:00 | The backend ends it. This should never be reached. |

Reaching the cap is reported as a fatal `BackendError`, because in our design it means
the wall clock above us failed. A clean interview ends 90 seconds before the runtime
would have had an opinion.

## 8. Memory: the two-minute problem

The model reliably remembers about two minutes of audio context. An interview is
fifteen. This is the single largest gap between what the model does and what we need,
and it is why `plan.md` insists the interview engine is a state machine rather than a
prompt.

The runtime's part of the answer is to make the session's context an explicit,
replaceable thing rather than an accumulating one. Three mechanisms, designed now,
implemented in the order they become necessary:

**Summary re-injection.** The interview engine holds the structured state — which rubric
dimensions have evidence, what the candidate claimed, what has already been asked. At
each turn boundary it can supply a compact briefing that is prepended to what the model
is working from. The model is not asked to remember; it is reminded. Turn boundaries are
the only safe place for this, because mid-response the model is mid-sentence.

**Session rollover.** When a session approaches either the context horizon or the frame
cap, the runtime can open a fresh session with a re-injected briefing and swap it in at
a turn boundary. The candidate hears a natural pause. This costs a prefill, so it
happens at a moment the interview engine chooses — after a question is answered, never
mid-thought. The protocol already supports it: a session is one connection, so rollover
is opening the next connection before closing the current one.

**Transcript as the real record.** Everything the model says and everything it hears is
recorded on our side as it happens. The model's own context is a working set, not the
record. If the model forgets minute two, the scoring pass does not, because scoring runs
over our transcript after the call, where latency does not matter and a larger model
can be used.

The first of these is cheap and is the one that matters for a demo. The second is
designed for and deliberately not implemented yet — it needs real hardware to tune the
rollover point, and a mistuned rollover is a worse demo than a forgetful agent.

## 9. Single conversation, single GPU

One call at a time per box. The model is batch-1 and stateful; there is no second
session to schedule. `GB10Backend.start_session` refuses to open a second session while
one is live rather than letting two conversations interleave into one model's state.

This is a capacity fact, not a bug to fix in software. The answer to "how do you scale"
is more boxes, which is also the business model.

## 10. What runs where, and what is untested

`services/agent/zeg/runtime/` is written to be read. It will not run on a laptop and has
not run on a box yet. Being honest about that in the source is part of the design:

| Module | Runs without a GPU | Tested here |
| --- | --- | --- |
| `runtime/protocol.py` | Yes, pure stdlib | Yes |
| `runtime/session.py` | Yes, pure state machine | Yes |
| `runtime/loop.py` | Yes, against a stand-in model | Yes |
| `runtime/codec.py` | Yes; pinning is a no-op off the box | Yes |
| `runtime/model.py` | No. Guarded, lazy, raises without CUDA | No |
| `runtime/server.py` | Needs a WebSocket library | Protocol layer only |
| `backends/gb10.py` | Yes, against a fake transport | Yes |

Every heavy import is inside a function. Importing `zeg` on a laptop with no GPU must
keep working, because that is how most of the repo gets developed, and the factory in
`backends/__init__.py` already imports `GB10Backend` lazily for exactly this reason.

What genuinely needs the box to validate: the per-frame cost budget, the endpointing
threshold against real candidates, time to first audio, whether the pre-roll length is
right, and the rollover point. None of those are knowable from here, and guessing them
in a document would just produce numbers someone later mistakes for measurements.
