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

## What you are building toward

`GB10Backend`, in `../agent/zeg/backends/`. The factory in
`../agent/zeg/backends/__init__.py` already imports that name lazily, so the moment
the class exists this works:

```bash
cd services/agent && PYTHONPATH=. ../../.venv/bin/python -m zeg.cli --backend gb10
```

Everything above the model is already written and tested. You are filling in one hole.

## Watch out for

- Wear headphones. An open mic next to a speaker produces a feedback loop that will
  eat an hour before anyone works out what is happening.
- Check host compatibility before anything else. The runtime is qualified against one
  specific driver and kernel, and the box may not match.
- The model's audio context is about two minutes. Do not be surprised when it forgets
  the start of a long conversation. Working around that is the agent service's job,
  not yours.
