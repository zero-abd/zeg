# services/speech — local model serving

**Owner: Hyunsuh (Track 1)**

Goal: the audio-to-audio speech model running on the Dell box, audio in from a
microphone, audio out to a speaker, in real time.

## What success looks like

You talk into a mic and something talks back, fast enough that it feels like a
conversation rather than a walkie-talkie. That is the whole bar for stage 1. No
interview logic, no scoring, no call joining.

## Start here

1. `SETUP.local.md` in the repo root. Untracked, has the weight download and the
   bring-up commands. Nothing works until the weights are on the box.
2. `../agent/zeg/backends/base.py`. This is the contract your work has to satisfy
   eventually. Read `AgentAudio`, `AgentText`, `UserTranscript` and
   `AgentInterrupted`, and note that the interface is full duplex: there is no "now
   it is the agent's turn" state.
3. `../agent/zeg/backends/mock.py`. A working implementation of that contract with no
   model behind it. It is the spec by example. When your real backend behaves like
   this one, it is done.

## What already exists

The runtime is written. It has not run on hardware. See `docs/11-runtime.md` for the
design and its honest tested-versus-untested table.

It lives in `../agent/zeg/runtime/` rather than under this directory, because the
client and the server share one protocol module and a protocol defined in two places
drifts. This directory is where bring-up notes, scripts and box-specific config go.

| Module | State |
| --- | --- |
| `runtime/protocol.py` | Written and tested, pure stdlib |
| `runtime/session.py` | Written and tested, pure state machine |
| `runtime/loop.py` | Written, budget accounting tested |
| `runtime/codec.py` | Written, pipelining tested |
| `runtime/model.py` | **Three seams raise. This is your job.** |
| `runtime/server.py` | Written, protocol layer tested, socket untested |
| `backends/gb10.py` | Written and tested against a fake transport |

## Your actual job

`runtime/model.py` has three marked seams that raise without CUDA. The checkpoint's
module code ships with the weights, so the last stretch of the model wrapper cannot be
written blind. Filling those in, and then making the numbers real, is stage 1.

Once it runs:

```bash
cd services/agent && PYTHONPATH=. ../../.venv/bin/python -m zeg.cli --backend gb10
```

Nothing above the model needs to change. The backend already satisfies the same
contract the mock does, and its tests mirror the mock's assertions so the two stay
interchangeable.

## Numbers that need the box

Every one of these is a guess in the source right now, and guessing them harder here
would just produce figures someone later mistakes for measurements.

- Per-frame cost against the 80 ms budget
- The endpoint threshold, against real candidates rather than a tone
- Time to first audio
- Pre-roll length
- The session rollover point

## Watch out for

- Wear headphones. An open mic next to a speaker produces a feedback loop that will
  eat an hour before anyone works out what is happening.
- Check host compatibility before anything else. The runtime is qualified against one
  specific driver and kernel, and the box may not match.
- The model's audio context is about two minutes. Do not be surprised when it forgets
  the start of a long conversation. Working around that is the agent service's job,
  not yours.
