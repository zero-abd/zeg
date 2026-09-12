# Compliance

Automated hiring tools are among the most heavily regulated uses of AI, and the rules
differ by the candidate's location, not the company's. This is not a late-stage checklist.
Several items below change the architecture, so they belong in the design phase.

**None of this is legal advice. Every item needs counsel review before a real candidate
is ever screened.**

## Rules that change the build

**New York City Local Law 144.** Automated employment decision tools used on NYC
candidates require an independent bias audit within the previous year, published results,
and candidate notice at least 10 business days in advance. The 10-day notice is a
scheduling constraint that reaches into the product: the system cannot screen someone
who was invited yesterday.

**Illinois Artificial Intelligence Video Interview Act.** Applies to video. Audio-only is
one of the reasons to stay audio-only, but confirm scope with counsel rather than assuming.

**Colorado AI Act and similar state laws.** Impose duties on developers and deployers of
high-risk AI systems in employment, including impact assessments and notice. Effective
dates have moved more than once; check the current status rather than a remembered one.

**EU AI Act.** Systems used for recruitment and candidate evaluation are classified
high-risk. That brings a conformity assessment, risk management, data governance, logging,
human oversight, and technical documentation obligations. If EU candidates are in scope,
this is the largest single compliance cost in the project and it must be scoped before
building, not after.

**Recording consent.** Two-party consent states and most of Europe require the candidate's
consent before recording. The greeting collects it explicitly. If consent is refused, the
call ends and routes to a human. There is no unrecorded mode, because the recording is the
evidence base for the score.

**Biometric law.** Voiceprints are biometric identifiers under Illinois BIPA and similar
statutes. If any component derives a speaker embedding, even for diarization, that is
biometric processing with its own consent and retention duties. **Design constraint:
prefer channel-based separation over speaker embeddings**, since the agent and the
candidate are on separate audio channels anyway. This one is easy to get wrong by
accident and expensive to discover later.

**Accessibility.** A voice-only screen excludes candidates with hearing or speech
disabilities. An accommodation path to a human screen must exist, be advertised before the
call, and be requestable without disclosing a diagnosis. Under the ADA this is not
optional.

## Non-negotiables

1. The candidate is told it is an AI within the first 20 seconds.
2. Recording consent is obtained before anything substantive is asked.
3. A human reviews every report before any adverse action.
4. A human-screen path exists and is offered, not buried.
5. The block list of prohibited questions is enforced in code, before synthesis.
6. Retention is bounded and documented, with deletion on request.

## Data handling

| Data | Where | Retained |
| --- | --- | --- |
| Call audio | Encrypted at rest, on the box | Shortest defensible period, likely 30 to 90 days |
| Transcript | Encrypted at rest, on the box | With the application record |
| Scores and evidence | Encrypted at rest, on the box | With the application record |
| Model weights | On the box | Pinned by version |

Nothing leaves the box except the report, over an outbound webhook the customer controls.
The on-premises design makes most data-residency questions answerable in one sentence,
which is a large part of the commercial case.

## Bias audit

Required by NYC law, and worth doing regardless. Independent auditor, annual, published.
Feed it the distributions described in the scoring doc. Budget both money and calendar
time; a real audit is not a week.

## The failure mode to fear

Not a lawsuit. A candidate posting a recording of the agent asking something tone-deaf,
or a journalist demonstrating that it scores one accent lower than another. The technical
controls above exist because the reputational exposure is larger and faster than the
legal exposure.
