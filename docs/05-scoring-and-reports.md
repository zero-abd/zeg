# Scoring and reports

Scoring happens after the call, not during it. Latency is irrelevant once the candidate
hangs up, so this pass can use a larger model, multiple samples, and the full transcript
at once.

## Pipeline

1. Finalize the transcript with a non-streaming ASR pass, which is meaningfully more
   accurate than the streaming one used live.
2. Segment into question and answer units, tied to timestamps.
3. Score each rubric dimension independently, in a separate call, each required to cite
   verbatim transcript spans as evidence.
4. Reconcile into a recommendation band.
5. Render the report.

Independent per-dimension scoring matters. Scoring all five at once lets one strong
answer color the rest, which is halo effect reproduced in a model.

## Evidence or it did not happen

Every score carries at least one quoted span with a timestamp. A dimension with no
citable evidence is recorded as "insufficient evidence", never as a low score. This is
the difference between a report a hiring manager can act on and a number they have to
take on faith, and it is also the thing that makes an adverse decision defensible.

## Recommendation bands

| Band | Meaning |
| --- | --- |
| Advance | Clear evidence across the weighted dimensions |
| Advance with reservations | Strong in some, thin in others, with the gap named |
| Insufficient signal | Call was short, connection poor, or candidate disengaged. Not a rejection. Offer a human screen. |
| Do not advance | Consistent absence of evidence across weighted dimensions |

"Insufficient signal" must be a real, frequently-used outcome. A system that forces every
call into advance or reject will manufacture confidence it does not have.

## Report format

One page. A recruiter reads it in 90 seconds.

- Recommendation band and the single sentence that justifies it
- Five dimension scores with one quote each
- Two or three notable moments, positive or concerning
- Topics that went uncovered, and why
- Full transcript, collapsed, with audio links

## Calibration

Without calibration the scores are decorative.

- **Seed set.** 50 recorded screens scored independently by two experienced engineers.
  This is the ground truth and it is expensive; budget for it early.
- **Agreement metric.** Cohen's kappa against the human advance/reject call. Under 0.6,
  the system is not shippable.
- **Drift watch.** Re-run the seed set on every model, prompt, or rubric change. Any
  regression blocks the change.
- **Score distribution.** Watch for compression toward the middle, the classic failure of
  model-as-judge. If 80 percent of candidates score 3, the rubric is not discriminating.

## Bias testing, engineering half

The legal half is in the compliance doc. The engineering half is:

- Matched-pair evals: the same answer content, delivered with different accents, names,
  speech rates, and gendered voices. Score deltas should be indistinguishable from noise.
- Score distributions sliced by any demographic data the customer already holds, checked
  against the four-fifths rule.
- ASR word error rate sliced by accent. A transcription gap becomes a scoring gap, and
  this is the most likely route by which bias enters the system.

That last point deserves emphasis. The most probable way zeg discriminates is not a
biased judgment model. It is an ASR model that transcribes some accents worse, feeding
the scorer a degraded version of what the candidate actually said.
