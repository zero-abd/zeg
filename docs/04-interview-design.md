# Interview design

Fifteen minutes is short. A human screener gets through perhaps four substantive topics.
The plan below assumes the agent is slower than a human at steering, so it budgets fewer
topics and more explicit transitions.

## The 15-minute plan

| Phase | Time | Purpose |
| --- | --- | --- |
| Greeting and consent | 0:00 to 1:00 | Identify as AI, state recording, confirm consent, set expectations |
| Warm-up | 1:00 to 3:00 | One recent project in their own words, establishes baseline fluency |
| Depth probe one | 3:00 to 7:00 | Drill into a claim from the warm-up, three to four levels deep |
| Depth probe two | 7:00 to 11:00 | A different rubric dimension, role-specific |
| Scenario | 11:00 to 13:30 | A short design or debugging situation, judgment under ambiguity |
| Candidate questions and close | 13:30 to 15:00 | Their questions, next steps, thank you |

The engine holds a hard wall clock. At 13:30 it transitions regardless of where the
conversation is, because running over is both rude and, for an automated system, a
consistency problem across candidates.

## Depth probing is the whole product

A screening call is worthless if it accepts the first answer. The pattern that separates
a real screen from a checkbox is recursive specificity:

1. Candidate claims something. "We moved to event-driven to handle load."
2. Ask what they personally did. Separates the team's work from theirs.
3. Ask for a number. Throughput, latency, instance count, data volume.
4. Ask about a tradeoff they accepted. Real work has costs; retellings often do not.
5. Ask what broke. Anyone who actually shipped it remembers.

Stop descending when the answer becomes specific and costly to fabricate, or when two
consecutive levels return generality. The second case is itself a strong signal, and the
engine should record it as evidence rather than treating it as a failed probe.

## Rubric dimensions

Five dimensions, scored 1 to 4. Role packs weight them differently.

| Dimension | What counts as evidence |
| --- | --- |
| Technical depth | Specific mechanisms, correct causal explanations, awareness of failure modes |
| Ownership | First-person accounts with detail a bystander would not have |
| Tradeoff reasoning | Names what was given up, not only what was gained |
| Debugging instinct | Forms a hypothesis before reaching for a fix |
| Communication | Structures an answer, checks understanding, adjusts to a follow-up |

Communication is scored on structure and responsiveness only. Accent, fluency, pace, and
vocabulary breadth are excluded by construction, and the scoring prompt states that
explicitly. Verify it with adversarial evals, not by trusting the instruction.

## Role packs

A role pack is a versioned file holding the question bank, dimension weights, seniority
calibration anchors, and the vocabulary boost list for ASR. Packs are reviewed in pull
requests like code, because changing one changes hiring outcomes.

Start with three: backend, frontend, and infrastructure or platform. Do not attempt a
general pack. The generality is what makes screens feel useless.

## Questions that must never be asked

The engine maintains a hard block list, enforced in code before any utterance reaches
TTS, not merely discouraged in a prompt. It covers age, family status, pregnancy,
national origin, citizenship beyond a single work-authorization yes or no, religion,
disability and health, arrest record, and current or past salary where prohibited.

The model will occasionally generate an innocent-seeming version of one of these while
building rapport. A classifier on the outbound text, run before synthesis, is the control.
Budget for its latency in the TTS path.

## Handling the awkward parts

**Silence.** After 4 seconds, a gentle prompt. After 8, offer to rephrase. After 15,
move on and record it.

**"Is this a real person?"** Answer truthfully and immediately. Offer the path to a human.

**Candidate distress or a bad connection.** Offer to reschedule with a human. Some
candidates will find the format alienating and should not be penalized for it.

**Off-topic or hostile.** One redirect, then a polite early close. Log it, do not score it.

**Suspected cheating.** An answer that sounds read aloud is not proof of anything and the
system should not accuse. Record the observation as a flag for the human reviewer,
phrased as an observation, never as a conclusion.
