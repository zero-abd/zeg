# Onboarding

Read this, then your track's README. Twenty minutes, and you can start building.

## Get it running first

```bash
make setup
make demo
```

That plays a full scripted screening call through a mock model and prints a
transcript. No GPU, no weights, no waiting. If that works, the whole repo works.

```bash
make test    # 24 tests
make web     # landing page dev server
```

## Layout

| Directory | What | Owner |
| --- | --- | --- |
| `services/agent/` | The interview brain. Conversation control, rubric, scoring. | Shared |
| `services/speech/` | Getting the model running on the box. | Hyunsuh |
| `services/gateway/` | Call joining, audio and video in and out. | Eunice |
| `web/` | Landing page. | Abdullah |
| `docs/` | Design decisions, with the reasoning kept. | Shared |

## Read in this order

**1. `plan.md`.** What we are building, the five stages, the timeline, and the five
things most likely to bite us. Everyone reads this. It is the only document where
disagreeing with it changes what we build tomorrow.

**2. `services/agent/zeg/backends/base.py`.** The most important file in the repo.
Every part of the system meets here. It defines what a speech model has to do:
consume audio frames continuously, and emit agent audio, agent text, caller
transcripts, and interruptions. The interface is full duplex on purpose, so there is
no "now it is the agent's turn" state anywhere in the design.

**3. `services/agent/zeg/backends/mock.py`.** The same contract, implemented with a
script and a sine tone instead of a model. This is how you build anything without
waiting for the GPU. It is also the spec by example: when the real backend behaves
like this one, it is correct.

**4. Your track's README.** `services/speech/README.md` or
`services/gateway/README.md`. Each one names the three files to read and the one
thing that will waste your morning if you get it wrong.

## The rest of the map

| File | When you need it |
| --- | --- |
| `services/agent/zeg/audio.py` | Frame format. Mono PCM16, 20 ms frames, stdlib only. |
| `services/agent/zeg/config.py` | Sample rates and call limits. |
| `services/agent/zeg/conversation.py` | How a call is driven end to end, and how latency is measured. |
| `services/agent/zeg/prompts.py` | The interview prompt, the consent text, the disclosure. |
| `services/agent/zeg/cli.py` | Entry point behind `make demo`. |
| `SETUP.local.md` | Weights and box bring-up. Untracked, not in git. |

## Design docs, if you want the reasoning

| Doc | Settles |
| --- | --- |
| `docs/04-interview-design.md` | The 15-minute structure, the rubric, how to probe an answer. |
| `docs/05-scoring-and-reports.md` | How a transcript becomes a 1-10 score with evidence. |
| `docs/03-latency-budget.md` | Where the milliseconds go. Note that it predates the model choice. |
| `docs/06-compliance.md` | The six things we do not negotiate on. |
| `docs/08-risks.md` | What kills this project, ordered by likelihood. |

## Four things that are not negotiable

These are in code or they are in `docs/06-compliance.md`. They are not style
preferences, and they are not the model's job to remember.

1. The candidate is told it is an AI within the first 20 seconds.
2. Recording consent is obtained before anything substantive is asked.
3. A human reviews every report. zeg recommends, it does not decide.
4. Prohibited questions are blocked in code before synthesis, not discouraged in a
   prompt.

The greeting and consent text are literals in `services/agent/zeg/prompts.py` for
exactly this reason.

## Conventions

- Commit in small steps. Subject line, then a body in prose explaining why, not what.
  The diff already says what.
- Comments explain reasoning, not mechanics.
- Do not add a dependency to `services/agent` without a reason. The mock path runs on
  a stock interpreter with nothing installed, and that is what lets everyone work
  without the box.
- Tests must pass before you commit. `make test`.
