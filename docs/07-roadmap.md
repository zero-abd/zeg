# Roadmap

Each phase exists to answer one question. If the answer is bad, the next phase does not
start. The phases are ordered so the cheapest disqualifying answers come first.

## Phase 0: Does the hardware hold up

**Question.** Can one Dell box run streaming ASR, a Nemotron-class model, and streaming
TTS concurrently, at p95 mouth-to-ear under 800 ms, over real telephone audio?

- Provision both candidate boxes, GB10 and RTX Pro 6000
- Confirm current model identifiers and licenses from the live catalogs
- Stand up the speech runtime and benchmark it under a real audio load
- Loop 8 kHz telephone-quality audio through end to end
- Produce the per-stage latency histograms

**Exit.** A measured latency table replacing the guesses in the budget doc, and a decision
on which box. If neither box clears 800 ms with all three models loaded, the on-premises
premise is in question and everything downstream changes.

## Phase 1: Does it hold a conversation

**Question.** Can it talk for 15 minutes without feeling broken?

- SIP termination and a real phone number
- Turn taking, barge-in, endpointing tuned on recorded human calls
- The interview state machine with the wall clock
- Scripted interview with no adaptive probing
- Record everything, build the replay harness

**Exit.** 20 internal volunteers complete a 15-minute call. Fewer than 1 in 10 turns has a
turn-taking failure. Volunteers describe it as awkward but not broken.

## Phase 2: Does it screen

**Question.** Does it agree with a good human screener?

- Adaptive depth probing
- One role pack, backend, built properly
- Post-call scoring with evidence citation
- The 50-call human-scored seed set
- Kappa measured against it

**Exit.** Kappa over 0.6 on the seed set. **This is the phase where the project most
likely dies**, and it should be reached as cheaply as possible for exactly that reason.

## Phase 3: Is it safe to point at real candidates

**Question.** Would we defend this in front of a regulator and a journalist?

- Question block list with the pre-synthesis classifier
- Matched-pair bias evals, ASR word error rate sliced by accent
- Consent flow, accommodation path, human review gate
- Counsel review against the compliance doc
- Independent bias audit engaged

**Exit.** Counsel sign-off. Bias evals show no significant score delta on matched pairs.
Audit is scheduled or complete.

## Phase 4: Can someone else run it

**Question.** Can a customer's IT team operate this without us?

- Recruiter console, scheduling, report delivery
- Applicant tracking system webhook
- Provisioning, monitoring, alerting, model version pinning
- Concurrency to the measured limit of the chosen box
- Runbooks and a support path

**Exit.** One friendly design-partner customer runs a real requisition end to end.

## Deliberately not on the roadmap

Multi-language, video, live coding, multi-tenant cloud, and custom rubric authoring by
recruiters. Each is a reasonable v2. Each would sink v1.
