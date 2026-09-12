# Hardware and models

Every number below is a starting hypothesis. None of it is settled until we benchmark
on the actual box with actual telephone audio. Treat the tables as things to disprove.

## The two Dell options

**Dell Pro Max with GB10.** NVIDIA Grace Blackwell superchip, 128 GB unified LPDDR5X.
Desk-sized, quiet, cheap to power. The catch is memory bandwidth: unified LPDDR5X is in
the high hundreds of GB/s, not the terabytes of a discrete card. Decode speed on an
autoregressive model is bandwidth-bound, so this box favors small models. Its large
unified pool is great for holding ASR, LLM, and TTS resident simultaneously without
eviction, which is exactly our access pattern.

**Dell Precision tower with an RTX Pro 6000 Blackwell.** 96 GB GDDR7 at multiple TB/s.
Several times the decode throughput, which buys either a larger model or more concurrent
calls. Costs more, draws more power, needs a real machine room.

The choice hinges on concurrency. One call at a time, the GB10 is likely enough and is a
far better story for a customer who wants a box under a desk. Eight concurrent calls
almost certainly needs the discrete card.

**Action: benchmark both before committing.** The specific measurement that decides it
is sustained decode tokens per second for our chosen model at batch sizes 1, 4, and 8,
with ASR and TTS running concurrently and competing for the same memory system.

## Model stack

| Stage | Candidate | Notes |
| --- | --- | --- |
| ASR | NVIDIA Parakeet, streaming variant | Fast, strong English, well supported in Riva |
| ASR alternative | NVIDIA Canary | Better on accented and multilingual speech, heavier |
| Reasoning | Nemotron Nano class, roughly 9 to 12 B, FP8 | Small enough to decode fast, strong reasoning for its size |
| Reasoning, offline scoring | Nemotron Super class, larger | Latency does not matter after the call ends |
| TTS | NVIDIA Magpie TTS, streaming | Low time-to-first-audio, interruptible |

NVIDIA's speech and Nemotron lineups move quickly and names change between releases.
**Before writing any integration code, pull the current NGC and NeMo catalogs and confirm
exact model identifiers, license terms, and whether a streaming checkpoint exists for
each.** Do not build against a name from memory.

Riva gives us a serving layer for ASR and TTS with the streaming and barge-in plumbing
already done. NeMo gives us the checkpoints and the fine-tuning path. Starting on Riva
and dropping to raw NeMo only where Riva blocks us is the cheaper path.

## Why the reasoning model stays small

Voice pace is roughly 150 words per minute, near 3.5 tokens per second of speech. A model
that decodes at 30 tokens per second stays comfortably ahead of the speaker and can
absorb a long first sentence before TTS starts. The binding constraint is not sustained
throughput, it is time to first token, and that is dominated by prefill over a growing
transcript. Keep the context tight: a running summary plus the last few turns verbatim,
not the whole call.

A larger model buys better judgment, which is what the rubric needs. Resolve this by
splitting the work: small model in the loop for conversation, large model after the call
for scoring. The candidate's experience is governed by the fast path, the report quality
by the slow one.

## Quantization

FP8 is the default. FP4 on Blackwell roughly doubles effective bandwidth and is worth
testing, but quantization damage shows up first in exactly the place we care about,
which is fine-grained judgment about a technical answer. Gate any FP4 adoption on the
eval harness, not on a latency win alone.

## Concurrency and capacity

| Box | Guess at concurrent calls | Confidence |
| --- | --- | --- |
| GB10 | 1 to 2 | Low, needs measurement |
| RTX Pro 6000 | 4 to 8 | Low, needs measurement |

Continuous batching in the inference server is what makes multi-call work. ASR and TTS
also consume GPU, and their cost scales linearly with calls while LLM cost batches well,
so at high concurrency speech models may dominate. Measure all three together.

## Failure and degradation

The box will fall over at some point mid-call. Decide now what happens:

1. Agent apologizes, states a human will follow up, ends the call cleanly.
2. Partial transcript is preserved and flagged for manual review.
3. The candidate is never left on a silent line. A watchdog on the media path ends the
   call after a few seconds of agent silence rather than letting it hang.

A fallback to a cloud API on failure would undo the entire on-premises premise. Do not
build one without an explicit customer decision.
