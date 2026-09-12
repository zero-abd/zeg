# Latency budget

The number that matters is mouth-to-ear: candidate stops speaking, to first sound of the
agent's reply reaching their ear. Under about 500 ms feels natural. Around 800 ms feels
like a slightly slow person. Past 1.2 s people start talking over the agent, which
cascades into barge-in handling and the call falls apart.

Target: p95 under 800 ms. Not the mean. The mean hides the turns that ruin calls.

| Stage | Budget, ms | Notes |
| --- | --- | --- |
| Inbound network and jitter buffer | 40 | Fixed cost of PSTN |
| Endpoint detection | 200 | Dominant, and mostly a policy choice |
| Final ASR after endpoint | 50 | Streaming means most work is already done |
| Engine decision | 10 | State machine, no model call |
| LLM time to first token | 250 | Prefill-bound, grows with context |
| TTS time to first audio | 120 | Streaming synthesis |
| Outbound network | 40 | |
| **Total** | **710** | Leaves 90 ms of headroom against target |

## Where the risk actually is

**Endpointing, 200 ms.** This is the largest single item and it is a tuning decision, not
a compute cost. Too eager and the agent interrupts someone drawing breath mid-explanation,
which is infuriating and reads as rude. Too patient and every turn feels sluggish. A
semantic endpointer that asks whether the partial transcript is a complete thought lets
us cut the silence threshold without interrupting. Budget real time for this; it is
the difference between a demo and a product.

**LLM prefill, 250 ms.** Grows with transcript length. At minute 14 the context is far
longer than at minute 1, so latency drifts upward through the call unless managed.
Mitigations: cache the system prompt and rubric with a KV cache that survives turns,
keep only the last few turns verbatim behind a running summary, and start generation
before the final ASR arrives when the partial is stable.

**Concurrency.** Every number above is single-call. Under batching, queueing delay
appears and p95 degrades much faster than the mean. The capacity question and the latency
question are the same question.

## Tricks worth building

- **Speculative start.** When the partial transcript has been stable for 150 ms, begin
  prefill. If the candidate resumes, discard.
- **Filler before substance.** A short acknowledgment lets TTS start while the model is
  still deciding. Use sparingly; constant "mm-hmm" is worse than a brief silence.
- **Precomputed audio.** Greeting, transitions, and the closing are fixed text. Synthesize
  them at startup and play from disk at zero latency.
- **Pin everything warm.** No model load, no cold start, no lazy CUDA context on the
  first call of the morning.

## How to measure

Instrument at the media layer, not in application logs, and record a timestamp at each
stage boundary for every turn. Ship a histogram per stage, per call. A single p95 number
for the whole system tells you something is wrong but never what.
