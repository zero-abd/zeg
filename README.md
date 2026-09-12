# zeg

A local AI interview agent. It joins a call, conducts a technical screening interview
for a software engineering role, and outputs a 1-10 assessment with quoted evidence.

Everything runs on one Dell box. Candidate audio never leaves the device, which is the
whole point: no third-party processor, no data-processing review, no per-interview fee.

It gathers evidence and recommends. A human makes the hiring decision.

**Start here: [plan.md](plan.md).** Background detail lives in [docs/](docs/).

## Barebone test, on your laptop, right now

No GPU, no model download, no dependencies. This runs a scripted interview through a
mock backend so you can see the shape of a call and work on everything above the model.

```bash
git clone https://github.com/zero-abd/zeg.git && cd zeg
python3 -m venv .venv && .venv/bin/pip install pytest
.venv/bin/python -m zeg.cli
```

If `zeg` is not importable, run it straight from the source tree:

```bash
PYTHONPATH=src .venv/bin/python -m zeg.cli
```

You get a timestamped transcript and a summary:

```
[00:00] agent  Hi, thanks for making the time. Before we start, two things you
               should know. I am an AI interviewer, not a person...
[00:18] caller yes that is fine
[00:18] agent  Thanks. Tell me about the hardest bug you shipped a fix for this year.
[00:28] caller a race condition in our payment reconciler
[00:28] agent  What did you personally do there, as opposed to the rest of the team?
...
backend            mock
call duration      64.7 s
agent speech       40.7 s
interruptions      1
reply latency      median 300 ms, p95 300 ms
```

Flags:

```bash
.venv/bin/python -m zeg.cli --quiet            # summary only, no transcript
.venv/bin/python -m zeg.cli --backend gb10     # real model, needs the box
```

Run the tests:

```bash
.venv/bin/python -m pytest -q
```

### What the mock is and is not

It imitates the *shape* of the real model: full duplex, partial then final transcripts,
barge-in, streamed audio at 22.05 kHz. Replies come from a fixed script and the audio is
a 220 Hz tone, not speech.

The clock is virtual. Time advances by the duration of each frame pushed, not by wall
clock, so a 15-minute call replays in under a second and the numbers are identical every
run. That makes it a regression test. **The latency figure is frame accounting, not a
measurement of anything.** Real latency needs the box.

## Real test, on the Dell box

The full pipeline needs the box, the GPU and the weights. Bring-up commands and the
weight download live in `SETUP.local.md`, which is untracked.

Once the speech runtime is up, point zeg at it:

```bash
.venv/bin/python -m zeg.cli --backend gb10
```

Wear headphones. A speaker and an open mic on the same machine produce a feedback loop
that will eat an hour before anyone works out what is happening.

## Layout

```
plan.md                 the end-to-end plan, read this first
docs/                   scope, architecture, latency, rubric, compliance, risks
src/zeg/
  audio.py              PCM16 frames, resampling, RMS. stdlib only.
  backends/base.py      full-duplex backend contract
  backends/mock.py      runs anywhere, no GPU
  conversation.py       harness, virtual clock, latency accounting
  prompts.py            greeting, consent, system prompt
  cli.py                zeg-converse
tests/                  24 tests, no GPU needed
web/                    landing page
```

## Team

| Who | Track |
| --- | --- |
| Abdullah (zero-abd) | Plans and artifacts, coordination |
| Hyunsuh (Tpl52-tech) | Model running locally, mic in, speaker out |
| Eunice (egs89-arch) | Call joining, video and audio ingestion |
