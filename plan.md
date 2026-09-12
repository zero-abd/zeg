# zeg — build plan

Local AI interview agent. Runs on a Dell dev box, joins a call, conducts a technical
screening interview, outputs a 1-10 assessment. Candidate audio never leaves the box.

Written 2026-09-12 from the team meeting.

> Third-party bring-up commands, weight downloads and runtime notes are in
> `SETUP.local.md`, which is untracked on purpose. This document covers what we build.

## 0. Tonight

Start the model download. It is 54 GiB and everything is blocked behind it. Commands in
`SETUP.local.md`. Hyunsuh owns this; confirm it finished before 8 AM.

## Getting started

Clone it and get a call running in two commands. No GPU, no weights, nothing to
install beyond a virtualenv.

```bash
git clone https://github.com/zero-abd/zeg.git && cd zeg
make setup
make demo
```

`make demo` plays a full scripted screening call through a mock model and prints a
timestamped transcript with latency. If that works, the repo works.

```bash
make test    # 24 tests
make web     # landing page dev server
```

Then read [ONBOARDING.md](ONBOARDING.md). It names the files to read in order and
points each person at their track. The short version: everything meets at
`services/agent/zeg/backends/base.py`, and `mock.py` next to it is that contract
implemented without a model, so it is the spec by example.

On the box, weights and bring-up are in `SETUP.local.md`, which is untracked. Start
that download before anything else; it is 12.6 GiB and everything is behind it.

| Track | Directory | Owner |
| --- | --- | --- |
| Interview brain | `services/agent/` | Shared |
| Model on the box | `services/speech/` | Hyunsuh |
| Call joining, A/V | `services/gateway/` | Eunice |
| Landing page | `web/` | Abdullah |

## Timeline

| When | What |
| --- | --- |
| Tonight | Repo access, model download, read this plan |
| 8:00 | Team assembled, box claimed, weights on it |
| 9:00 | Hackathon starts |
| End minus 2h | Stop building, start demo prep |

## 1. Product

SMBs cannot afford $10 per interview from the incumbents. A $5K box amortises against
roughly $15K a month of SaaS. The differentiator is not the AI, it is that candidate
audio stays on the device, which removes the third-party data-processing problem from
the customer's compliance review entirely.

Demo: a candidate joins a link, talks to the agent for a few minutes, the agent probes
a technical claim rather than accepting the first answer, and the recruiter gets a score
with the quotes that justify it.

zeg gathers evidence and recommends. A human makes every hiring decision.

## 2. Architecture

```
browser (candidate)  ──WebRTC──►  zeg bot  ──local socket──►  speech model
   mic + speaker                  prompt,                      on the Dell box
   static image                   interview logic,
                                  memory, wall clock
                                       │
                                       └──► transcript ──► score 1-10 ──► recruiter view
```

Everything in that diagram runs on one machine. The only thing crossing the network is
the candidate's own WebRTC connection.

**Recommendation: browser client first, Google Meet as a stretch.**

The meeting put Google Meet as the primary and a custom hosted site as the fallback.
Invert that. Google Meet has no supported way for a bot to join and access raw audio;
the realistic implementation is headless Chrome with virtual audio devices, which is a
full day of work that fails in ways that are hard to debug under time pressure.

A browser client over WebRTC is a few hours, it is the same audio path, and it demos
identically. Attempt Meet only once the interview works end to end. If it lands it is a
great beat. If it does not, nothing is lost.

Fallback if audio-to-audio will not run at all: the cascade. Streaming transcription,
local LLM, text to speech. Slower, more moving parts, every piece known to work. Keep it
in your back pocket; do not build it pre-emptively.

## 3. Five stages

**Stage 1 — model running locally.** Bring the runtime up, open the client, talk to it
through headphones. Success is a conversation, not a benchmark.

**Stage 2 — our voice in its mouth.** Replace the demo prompt with the interview prompt,
already drafted in [src/zeg/prompts.py](src/zeg/prompts.py). Hot-reload the bot so
iteration is seconds, not minutes.

**Stage 3 — end to end.** Candidate opens a link, interview runs, transcript captured.
Remote browsers need HTTPS, because microphones are blocked on insecure origins
anywhere but localhost.

**Stage 4 — the score.** After the call, a separate pass over the transcript produces
1-10 plus the quotes behind it. Latency does not matter here, so use a bigger model or
more sampling. This is the artifact the recruiter actually sees, so it deserves more
polish than its position in this list suggests.

**Stage 5 — eye tracking, if time allows.** MediaPipe, flag gaze beyond 30-45 degrees
for over 5 seconds, save the clip for recruiter review. Genuinely impressive in a demo.
Also the first thing to cut. It needs the video channel, which the audio path does not.

## 4. Work division

| Who | Track |
| --- | --- |
| Abdullah | Plans and artifacts, coordination, floating |
| Hyunsuh | Track 1: model running locally, mic in, speaker out |
| Eunice | Track 2: call joining, video and audio ingestion |

Agents write the code. The team monitors, debugs, unblocks.

Eunice being ECE is worth spending on Stage 5 and on any audio device problem on the
box, which is where hackathon hours usually disappear.

## 5. What will actually bite

Measured limits of the speech runtime, not speculation. Details in `SETUP.local.md`.

**The model remembers about two minutes.** It is trained with short audio context and
does not reliably retain more. A long interview forgets its own opening. Two responses:
keep demo interviews to about five minutes, and make our layer the memory. The engine
holds the structured state, which rubric dimensions have evidence, what the candidate
claimed, and re-injects a compact summary rather than trusting the model to remember.

This is why the interview engine is a state machine and not a prompt. That was a design
preference a week ago. The context window makes it a requirement.

**One conversation at a time.** Single client, single GPU. Fine for a demo. Be honest
about it if a judge asks about scale; the answer is more boxes, which is also the
business model.

**Sessions cap around 16 minutes.** Hard limit in the runtime. Our wall clock wraps up
before it, so we never hit it mid-sentence.

**The checkpoint is research-grade.** Documented behaviour includes skipping tools,
calling the wrong one, canned-reply loops, and dropped transcript words. Keep tool use
minimal in the demo. Anything that must be reliable lives in our code, not in the
model's function head. The prohibited-question check is ours and runs before synthesis.

**The Dell box may not be a qualified host.** The runtime is qualified against one
specific driver and kernel. A different one is, in the vendor's words, a new
qualification target. Check host compatibility in the first ten minutes. This is the
single most likely thing to cost us the morning.

**Turn latency may feel slow.** Endpointing is tuned for natural human pauses at around
1.6 seconds. Retuning voids the qualification. Listen to it before deciding it is a
problem.

## 6. What we build

| Component | State |
| --- | --- |
| Full-duplex backend contract | Done, `src/zeg/backends/base.py` |
| Mock backend, no GPU needed | Done, `src/zeg/backends/mock.py` |
| Conversation harness, 24 tests | Done, `src/zeg/conversation.py` |
| Interview prompt and consent text | Done, `src/zeg/prompts.py` |
| Real backend | Written, untested on hardware |
| Interview engine: plan, clock, memory, briefing | Done, 20 tests |
| Call driver: consent, clock, briefing, gating | Done, 23 tests |
| Session rollover and seeding | Done, 21 tests, needs the box to tune |
| Prohibited-question block list | Done, 24 tests |
| Serving runtime design | Done, `docs/11-runtime.md` |
| Serving runtime implementation | Written, 100 tests, needs the box |
| Scoring pass and report | Done, 22 tests, model-free judge |
| Landing page | Done, builds clean |

## 6a. Progress log

Newest first. Each entry is one commit or a short run of them.

**Session rollover.** `services/agent/zeg/memory.py` decides when to replace the model
session and what to prime the new one with. The policy is conservative on purpose: only
at a turn boundary, never twice in quick succession, and never while a probe is still
descending, because the descent is exactly the thread a fresh session would lose. The
seed carries the standing rules, the briefing and the last exchange, so there is no seam
the candidate can hear. Every number in it is a starting point; the real rollover point
needs the box.

Writing it surfaced a genuine bug in the engine. Every specific answer was starting a
new claim, so the probe ladder reset each turn and never got past its first rung. An
answer to an outstanding probe now deepens the claim being probed.

**The parts became one system.** `services/agent/zeg/interview.py` drives a call:
backend events in, actions out. It owns the consent gate, the wall clock, re-grounding
the model when a briefing goes stale, and dropping any prohibited question before it
reaches synthesis. It is a pure state machine with no I/O, so consent, the time limit
and the block list are testable without a model, a socket or a microphone, which is the
only way they stay tested. Its record feeds the scoring pass with no translation.

**Post-call scoring.** `services/agent/zeg/scoring.py` turns a transcript into a 1-10
assessment with quoted evidence. Dimensions are judged one at a time so a strong answer
cannot lift the rest, and a dimension with no citable span is recorded as insufficient
evidence rather than a low score. "Insufficient signal" is a real outcome with its own
band. A model-free judge makes the whole pipeline demoable and testable today; a
model-backed judge drops into the same interface. `make demo` now prints the report.

**Serving runtime implemented.** `services/agent/zeg/runtime/` is the model-side
process: wire protocol, session lifecycle, the frame loop with explicit budget
accounting, and the audio codec. `backends/gb10.py` is the client half. The client owns
turn boundaries and the server owns continuous model state, because the model's own
endpointer is tuned for ordinary conversational pauses and an interview is precisely
where a long pause means thinking rather than finishing. Endpointing is therefore an
interview design decision, not a model default. 100 new tests, all against a fake
transport. The model wrapper has three seams that need the box.

**Interview engine and question block list.** `services/agent/zeg/engine.py` holds the
plan, the wall clock, what the candidate claimed and which rubric dimensions still
lack evidence. `briefing()` is the answer to the two-minute context window: a compact
restatement handed back at a turn boundary, so the model is reminded rather than asked
to remember. `blocklist.py` gates every outbound utterance against nine categories of
prohibited question, in code before synthesis, with work authorisation explicitly
permitted and unable to shield an unlawful clause in the same breath. 44 new tests.

**Serving runtime design.** `docs/11-runtime.md` settles the two-process split, the
80 ms frame, who decides a turn has ended, barge-in cancellation, the wire protocol,
the watchdog, the session frame budget and the memory strategy. It is explicit about
what has not run on hardware.

**Monorepo split.** One directory per track, a Makefile so setup is two commands, and
`ONBOARDING.md` naming the files to read in order.

**Repo scrubbed and pushed.** Vendor project names, checkpoint ids and dependency pins
are out of the tracked tree and out of the commit history, and live untracked in
`SETUP.local.md`.

**Foundation.** Audio frames, the full-duplex backend contract, a mock backend that
needs no GPU, the conversation harness with a virtual clock, and the interview prompt
with its consent text.

## 7. Demo script

Two hours at the end, per the meeting.

1. The box. It is right there, unplugged from the internet if we are feeling brave.
2. A candidate joins and talks. Real conversation, interruptions included.
3. The agent probes a claim instead of accepting the first answer.
4. The score, with quotes.
5. The cost slide. $10 per interview versus a box that already paid for itself.
6. Eye tracking, if it exists.

The compliance angle is the strongest non-technical beat. Say plainly that no candidate
audio left the device.

## 8. Open

1. Which Dell box, exactly. Blocks the model choice. Ask at handout.
2. Is the download done. Hyunsuh.
3. Who transfers weights to the lab box. One person, first thing.
4. Headphones. Everyone. Feedback loops will otherwise eat an hour.
5. Google Meet: attempt at all, or commit to the browser client. Recommend the latter.
