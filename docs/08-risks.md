# Risks

Ordered by how likely they are to end the project, not by how dramatic they sound.

## 1. The scores do not agree with humans

The kappa target of 0.6 is not obviously reachable. Human screeners disagree with each
other substantially, so there may not be a stable target to hit. If two experienced
engineers only agree with each other at 0.5, asking a model to beat that is incoherent.

*Mitigation.* Measure human-to-human agreement on the seed set first, before measuring
the system against it. That number sets the realistic ceiling and it is cheap to obtain.
Do it in Phase 2, first week. If it comes back low, reframe the product as structured
evidence gathering rather than scoring, which is a smaller but still real product.

## 2. Candidates hate it

Being screened by a machine for a job you want is an unpleasant premise, and some
candidates will refuse or disengage. The best candidates have the most options and are the
most likely to decline, which would invert the selection the product exists to perform.

*Mitigation.* Measure opt-out rate and post-call sentiment from Phase 1. Segment by
seniority; if senior candidates opt out at high rates, the product is junior-screen only,
which is a smaller market but an honest one.

## 3. Latency does not close on a single box

Three models sharing one memory system, under concurrency, with a safety classifier in
the outbound path. The budget has 90 ms of headroom, which is thin.

*Mitigation.* Phase 0 exists for this. Fallbacks in order: smaller reasoning model, a
second GPU, drop concurrency to one call per box and sell more boxes.

## 4. Compliance cost exceeds the product

EU high-risk conformity assessment, an annual independent bias audit, and counsel review
per jurisdiction. For a small team this can exceed engineering cost.

*Mitigation.* Scope v1 to US-only, and within the US to states whose requirements are
already understood. Get a real quote for a bias audit during Phase 0, when it is still
cheap to change course.

## 5. ASR bias becomes scoring bias

The most likely technical route to discriminatory outcomes, and the least visible. Word
error rate varies by accent; the scorer sees degraded text and scores it lower.

*Mitigation.* Slice word error rate by accent from Phase 0, not Phase 3. If the gap is
large, it constrains the ASR choice and possibly the market. Treat it as a design input.

## 6. The model asks something it should not

A single clip of the agent asking about family status is a worse day than any outage.

*Mitigation.* Enforcement in code before synthesis, not prompt instruction. Adversarial
red-team evals in the regression suite. Accept the latency cost.

## 7. Depth probing is harder than it looks

Recursive specificity requires knowing when an answer is genuinely specific, which is
close to the full difficulty of technical interviewing. A model that probes badly is worse
than a scripted one: it wastes the 15 minutes and frustrates good candidates.

*Mitigation.* Phase 1 ships scripted deliberately. Adaptive probing is measured against
the scripted baseline, and if it does not beat it on kappa, it does not ship.

## 8. The upstream model lineup moves under us

Names, checkpoints, and licenses in the open speech-model families change between
releases. Building against a remembered name produces code that does not run.

*Mitigation.* Pin exact versions in ops config. Confirm identifiers from the live catalog
at the start of Phase 0. Re-run the full eval suite on any model bump.

## 9. Fifteen minutes is the wrong length

Long enough to be a burden on the candidate, possibly too short for real signal.

*Mitigation.* Make duration a role-pack parameter from the start rather than a constant.
Test 10 and 20 minutes against kappa in Phase 2. Let the data pick.
