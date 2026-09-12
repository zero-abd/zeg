# zeg

An autonomous voice interviewer that conducts technical screening calls for software
engineering roles. It runs entirely on a single Dell workstation on the customer's own
premises: speech recognition, the reasoning model, and speech synthesis are all local,
so candidate audio never leaves the building.

Each call is capped at 15 minutes and produces a structured, rubric-scored report with
evidence citations back into the transcript.

**Status: planning only.** No code yet. Nothing in this repo is committed until the
design below is agreed.

## Why on-premises

| Concern | Cloud voice API | zeg |
| --- | --- | --- |
| Candidate audio leaves the org | Yes | No |
| Per-minute cost at 10k screens/yr | Meters forever | Fixed hardware cost |
| Round-trip latency floor | Internet RTT included | LAN only |
| Vendor model swap under you | Common | Pinned, versioned locally |
| GDPR/biometric data residency | Contractual | Physical |

## Documents

| Doc | What it settles |
| --- | --- |
| [Vision and scope](docs/00-vision-and-scope.md) | Who it is for, what it will not do |
| [Architecture](docs/01-architecture.md) | Components and the path audio takes |
| [Hardware and models](docs/02-hardware-and-models.md) | Which Dell box, which Nemotron, sizing |
| [Latency budget](docs/03-latency-budget.md) | Where the 800 ms goes |
| [Interview design](docs/04-interview-design.md) | The 15-minute structure and question bank |
| [Scoring and reports](docs/05-scoring-and-reports.md) | Rubric, calibration, output format |
| [Compliance](docs/06-compliance.md) | Hiring law, consent, bias audit |
| [Roadmap](docs/07-roadmap.md) | Phases and what each one proves |
| [Risks](docs/08-risks.md) | What is most likely to kill this |
| [Open questions](docs/09-open-questions.md) | Decisions still owed |

## Team

| Who | Focus |
| --- | --- |
| zero-abd | Owner |
| Tpl52-tech | Invited, write access |
| egs89-arch | Invited, write access |
