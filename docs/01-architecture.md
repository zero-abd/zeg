# Architecture

## The path one turn of audio takes

```
PSTN ──► SIP trunk ──► [ the Dell box ]
                         │
                         ├─ Media gateway        RTP in, jitter buffer, Opus/G.711 decode
                         ├─ VAD + endpointer     is the candidate still talking
                         ├─ Streaming ASR        partial and final transcripts
                         ├─ Turn manager         may I speak now, or was that a pause
                         ├─ Interview engine     state machine over the 15-minute plan
                         ├─ Reasoning model      next utterance, given plan plus history
                         ├─ TTS                  streamed audio chunks
                         └─ Media gateway        RTP out
                         │
                         └─ Recorder ──► encrypted local store ──► post-call scoring
```

Everything inside the box is one process tree on one host. The only network egress in
normal operation is the SIP trunk and, optionally, an outbound webhook to the customer's
applicant tracking system.

## Components

**Media gateway.** Terminates SIP and RTP. Candidates are on phones, so expect 8 kHz
G.711 much of the time; upsample rather than assume wideband. LiveKit, FreeSWITCH, or
Asterisk all work. Prefer whichever gives the cleanest barge-in control, because
barge-in is the single most visible quality signal in a voice agent.

**Voice activity detection and endpointing.** Cheap VAD on every frame. Endpointing is
the hard part: a fixed 700 ms silence threshold makes the agent either interrupt people
mid-thought or feel sluggish. Plan for a semantic endpointer that also considers whether
the partial transcript is syntactically complete.

**Streaming ASR.** Partial hypotheses drive the endpointer; finals drive the transcript.
Must handle technical vocabulary, which general models mangle. Budget for a domain
boosting list of a few thousand terms: Kubernetes, idempotent, gRPC, mutex, and every
framework name in the role description.

**Turn manager.** Owns the microphone. Decides when the agent speaks, cancels in-flight
TTS on barge-in, and inserts backchannels so silence does not read as a dropped call.

**Interview engine.** A state machine, not a prompt. It holds the 15-minute plan, the
remaining time budget, which rubric dimensions still lack evidence, and which follow-ups
are legal to ask. It calls the reasoning model to phrase things; it does not delegate
control flow to the model. This separation is what makes the interview auditable.

**Reasoning model.** Given the current plan step, the transcript so far, and the rubric
dimension under test, produce the next thing to say. Constrained decoding into a small
schema so the engine always knows what the model intended.

**Text to speech.** Streaming, low time-to-first-audio, interruptible mid-utterance.
One consistent voice. No attempt to sound human enough to deceive.

**Recorder and scorer.** Writes encrypted audio and transcript locally. After the call,
a separate non-realtime pass scores against the rubric with a larger model or more
generous sampling, since latency no longer matters.

## Why the engine is a state machine

A model that freely decides what to ask next will drift, run long, repeat itself, and
occasionally ask something a lawyer will not enjoy reading. Putting time budget, topic
coverage, and question legality under explicit program control means the model's job
shrinks to phrasing and evaluation, which it is good at.

## Repository layout, proposed

```
zeg/
├── docs/
├── gateway/        SIP and RTP, barge-in, audio framing
├── pipeline/       VAD, ASR, TTS wrappers, warm model handles
├── engine/         interview state machine, plans, time budget
├── rubrics/        role packs, versioned, reviewed like code
├── scoring/        post-call evaluation and report generation
├── ops/            provisioning, model pinning, health checks, dashboards
├── evals/          recorded calls, replay harness, kappa tracking
└── web/            recruiter console
```

`evals/` matters more than it looks. Without a replay harness over recorded calls, every
prompt or model change is a guess.
