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

SMBs cannot afford $10 per interview from the incumbents. A $10K box amortises against
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
| Steering: say and steer, client to model | Done, routed through the server loop |
| Interview engine: plan, clock, memory, briefing | Done, 20 tests |
| Call driver: consent, clock, briefing, gating | Done, 23 tests |
| Session rollover and seeding | Done, 21 tests, needs the box to tune |
| Engine-driven demo, end to end | Done, 15 integration tests |
| Prohibited-question block list | Done, 24 tests |
| Serving runtime design | Done, `docs/11-runtime.md` |
| Serving runtime implementation | Written, 100 tests, needs the box |
| Scoring pass and report | Done, 47 tests, model-free and model-backed judges |
| Eval suite and agreement instrument | Done, 16 tests, `make evals` |
| Matched-pair bias evals | Done, 18 tests, `make bias` |
| Block-list red team | Done, 51 tests, `make redteam` |
| Consent gate red team | Done, 42 tests, `make consent` |
| Landing page | Done, builds clean |

## 6a. Progress log

Newest first. Each entry is one commit or a short run of them.

**Answering a consent question counts as the repeat.** A regression from the entry below, found by
checking the new timer against the other consent paths: both answers end with the question, so a
candidate who asked "what happens to the recording?" at 15 s heard the question again at 22 s, seven
seconds later. Answering now marks the question as repeated and restarts the wait from there, so the
call ends at 30 s if nothing follows. One new test, failing on the previous commit. Suite: 1373
passed.

**The consent question is asked once more before silence ends the call.** Measured: the disclosure
finished at 13 s and the call ended at 27 s, never repeating the question. Silence there is often a
candidate who did not hear it or is still deciding, and they lost the interview for it. It is now
repeated after 7 s of quiet, once, and the full 15 s wait runs again from the repeat, so the call
ends at 34 s instead. The wait is measured from the repeat as well as from what was last heard, so it
does not depend on a backend reporting our own line's audio back to us. Three new tests; all fail on
the previous commit. Two existing tests changed with the reason recorded: the timeout test now ends
at 34 s, and a silent call's duration bound moved from 60 s to 75 s. One more was changed because it
drove the clock to 14 minutes with consent unsettled, a state a real call cannot reach; it now
asserts no wrap-up rather than no actions at all. Suite: 1372 passed.

**A lone "1" is a figure only when it measures something.** A new recognition degradation, spoken
numbers written as digits, found the score moving up: the lean transcript went 7/10 to 8/10 because
"we isolated it to one merchant" became "1 merchant" and counted as a figure. The word was
deliberately excluded ("one of the things" is not a measurement) and the digit was not, so the same
answer scored 3 or 4 on technical depth depending on how the recogniser wrote it. A bare 1 now reads
as the word unless something is measured by it: "1 ms", "1 second", "1%", "1.5x", "1,200" and "1
outage in 2 years" all still count; "1 merchant" and "version 1" do not. Nine new cases plus the
degradation; three fail on the previous commit. Suite: 1370 passed.

**Four prohibited questions that got through are blocked; a product feature is not.** A batch through
the guard found "Are you a US citizen?" (a word between the article and the noun), "What is your
religion?" (only "what religion" was matched), "When did you graduate from college?" (only "what year
did you graduate") and "Is English your first language?" (only the "what is your" phrasing) all
reaching a candidate in full. Each is now caught, along with "Are you an Irish national?" and "Are
you disabled?". The health rule matched any mention of disability, so "how did you test the
disability accommodations feature" was cut off with a redirect; it now has to be directed at the
candidate. Accepted over-blocks, since a false block costs one rephrased question: "When did you
graduate the rollout to all users?" and "Is Go your first language at work?". Eight new cases; seven
fail on the previous commit. Suite: 1358 passed.

**Stop and person requests: nine false endings removed, three missed requests heard.** A batch of
technical answers and real requests through the mid-interview checks found both directions wrong.
Ending the interview on an ordinary answer: "I'd like to stop and think about that", "please stop me
if this is too much detail", "I want to stop there, that's the gist", "we end the call when the
websocket drops", "let's stop the recording of logs at debug", "I'd like to end on that point", "I
want to talk to someone on the SRE team", "can you put me through the question again", "hand me over
the next question". Missed: "I don't want to continue", "I don't want to do this anymore", "is there
a person / someone I can talk to?". Each rule was narrowed or added for its own case (a bare stop
followed by "and", "me" or "there"; "the call" only when asked for; "the recording of" something
else; someone on, at or in a place; put through or transfer only to someone or at the end). "Could I
talk to someone from your platform team" is still a person request, on purpose: the policy leans
towards honouring one. Nineteen new cases; thirteen fail on the previous commit. Suite: 1350 passed.

**Seven more plain agreements are consent.** A batch of 47 realistic replies to the recording
question found eight read as refusals, each ending the call: "no, that's fine", "I don't have a
problem with that", "all good", "I'm good with that", "you can record", "you may record it", "feel
free", and "why not". The first seven are now clear yeses. "why not" is left a refusal on purpose: it
is also a question, and consent needs a clear yes. The gate is still asymmetric, so each addition
came with its dangerous neighbours added to the refusal corpus and checked: "no, it's fine not to
record", "you may not record", "feel free to not record me", "you can't record this", "I'm not good
with that", "I do have a problem with that", "no, that's not fine", "all good, but please don't
record". A "not (to) record" refusal pattern was added for two of them. Fifteen corpus cases; the
seven yeses fail on the previous commit, the refusals pass on both. Suite: 1331 passed.

**Asking for time is a hesitation, so it no longer ends the call at the consent question.** Measured:
"hmm, let me think", "good question, give me a second" and "uh, hold on", said to the recording
question, were read as not agreeing; the call ended as declined and the candidate was told a person
would be arranged instead. Only bare sounds counted as hesitating. The shared definition now also
treats a turn made only of sounds and requests for time as a hesitation, so the consent gate waits,
the probe ladder is not used up, scoring does not pair it as an answer, and the rollover seed leaves
it out. A turn with content in it ("good question, we used kafka") is still an answer. This also
closes the gap noted in the entry below. Four new tests; the three consent cases fail on the previous
commit. Suite: 1301 passed.

**A turn that stops mid-thought is held like a hesitation.** Only a turn holding nothing but "um" got
the longer endpoint, so "uh, let me think", "so the reason was, uh" and "we sharded it because"
committed at the ordinary 640 ms pause and the model answered someone still thinking. The client
now also holds a turn whose text so far ends on a filler, a conjunction or an article, or on a
request for time ("let me think", "good question"). The trailing-word list is short on purpose:
"I think so", "back then" and "we turned it on" are finished and still commit at the usual pause.
Six new cases; the three mid-thought ones fail on the previous commit. Not changed: once the hold
runs out, the interview still treats "uh, let me think" as an answer. Suite: 1297 passed.

**Elided judge quotes stay rejected; the judge is told not to elide.** The open case from the entries
below, decided rather than loosened: accepting parts joined with "..." would let an elision reverse
who did the work ("I didn't write ... the fix" from "I didn't write the tests, Sam wrote the fix"),
which is exactly what the quote check exists to stop. The judge prompt now asks for one continuous
passage, so an honest judge is not voided for eliding, and a test pins both the rejection and the
instruction (the instruction half fails on the previous commit). Suite: 1291 passed.

**A unit written against its number does not void a judge quote.** "p99 dropped to 30ms" quoted from
"30 ms", or "12 GB" from "12GB", was not found and the score was voided. A number and the letters
written straight after it are now split on both sides of the comparison; "p99" stays one token and a
different number ("300 ms") still fails. Three new cases; the two spacing ones fail on the previous
commit. The ellipsis case noted below is still open. Suite: 1290 passed.

**A judge quote with the filler tidied out is not a fabrication.** The quote check ignored case,
spacing and punctuation but not filler, so "I wrote the retry budget myself after the outage", quoted
from "I, uh, wrote the retry budget myself, you know, after the outage", voided the score. Recognised
speech is full of these and judges routinely tidy them. Pure filler (um, uh, er, ah, "you know") is
now dropped on both sides; hedges are not, so "I kind of led the rollout" quoted as "I led the
rollout" still fails. Found alongside, not fixed here: a unit spacing difference ("30ms" for "30 ms")
and a quote joining two parts of an answer with an ellipsis are also voided. Two new tests: the
filler case fails on the previous commit, the hedge guard passes on both. Suite: 1287 passed.

**What the candidate says after the wrap-up is not a claim.** Turns past the wrap-up were still
noted by the engine, so "I'd love to hear more about how on-call works for the team" and "okay great,
that sounds really reasonable to me" became claims (measured), and any briefing in the close listed
them as what the candidate had claimed. Scoring already excluded them through the interview window;
the engine now does too. One new test, failing on the previous commit. Suite: 1285 passed.

**A candidate with no questions at the wrap-up is thanked and the call ends.** Nothing ended a call
between the wrap-up and the time limit: measured, "no, I think I'm good, thanks" at 13:40 was followed
by 76 seconds of silent, recorded line and then "We're out of time", and the "no" went into the
briefing as a claim. After the wrap-up, a short turn that plainly says there is nothing more ("I'm
good", "that's all", "no questions", "nothing else"), or a bare "no" in direct reply to the wrap-up
question, now gets a closing line and ends the call as "completed". A question, a longer turn, "I'm
good at Go", or a "no" to some other question does not. Six new tests; the three closing cases fail
on the previous commit, the three that must not close are guards. Suite: 1284 passed.

**A fixed line on its way counts as the agent speaking.** The client only knew the agent was speaking
once the runtime reported the response started, so straight after `say()` both `agent_speaking` and
`caller_speaking` were false (measured). A rollover waiting for quiet, as the driving contract tells
every driver to do, could close the session in that gap and the line was never heard: for example the
redirect spoken over a prohibited question, once the cancelled reply ended. A sent, unstarted line now
counts, for at most 3 s so a lost one cannot hold off rollovers, and a refused one stops counting. It
is kept out of the barge-in check, since nothing is playing yet to interrupt. Four new tests: the
line counting fails on the previous commit, the bound test only because the setting did not exist,
and two guards (refusal, no barge-in) pass on both. Suite: 1278 passed.

**A briefing no longer says an answer held what it was asked for when it did not.** Answers are kept
under their probe whenever they are not vague, and were labelled by the probe: measured, "the figure:
it was faster afterwards" and "their own part: we sharded it by merchant". A fresh session reads that
as covered and does not ask again. Each answer is now checked for what its rung asks, with the
scorer's own markers (ownership, a number spoken or written, a tradeoff, any evidence for what
broke), and one without it reads "asked for the figure, not given: ...". The existing labels are
unchanged for answers that do hold it. One new test, failing on the previous commit. Suite: 1274
passed.

**A probe issued alongside a rollover survives it.** At the hard horizon one answer produces both a
probe and a rollover (measured at 2:02 of a call whose ladder kept descending). The probe was
steered into the session about to be closed, the seed never mentioned it, and the engine still
treated it as outstanding, so the next answer was filed under a question the fresh session had not
been told to ask. The seed now carries an unanswered probe, worded so a session that can see it was
already asked does not ask it twice. Two new tests: the carried probe fails on the previous commit;
a guard shows an answered probe is not carried. Suite: 1273 passed.

**A gap in a dimension the role ignores does not hold back the band.** "Advance" requires no
dimension without evidence, and that check ignored role weights: under a role weighting
communication zero, a candidate at 10/10 on everything the role counts was held at "advance with
reservations" for not speaking to communication. The band now looks only at dimensions the role
counts; under the generic role the same gap still holds it back. One new test, failing on the
previous commit. Suite: 1271 passed.

**A role that weights a dimension zero cannot crash the report.** When every dimension with evidence
was one the role pack weighted zero, the overall divided by zero and the report for a finished call
raised. Only dimensions the role counts now count toward the minimum of three, since a zero-weighted
one adds nothing to the overall; such a call is "insufficient signal", and the flag counts against
the dimensions the role uses. One new test, raising ZeroDivisionError on the previous commit. Suite:
1270 passed.

**A halfway overall score always rounds up.** The 1-4 mean was mapped onto 1-10 with round(), which
rounds halves to even, so exactly-halfway profiles went both ways: 4,4,3,3 showed 8 from 8.5 and
2,2,1,1 showed 2 from 2.5, while 3,3,2,2 showed 6 from 5.5. No band boundary is crossed in these
cases with equal weights, but the number a reviewer compares across candidates was inconsistent.
Halves now round up. Three new cases; the two that rounded down fail on the previous commit. Suite:
1269 passed.

**Agreeing over the answer to a consent question is consent.** Before consent, every interruption
was taken as the candidate talking over the disclosure. A candidate who heard it through, asked
"what happens to the recording?", and said "oh okay, that's fine" over the answer had that consent
discarded, heard the whole greeting again, and was flagged for talking over the disclosure. The
interview now notes when the candidate has replied to the disclosure having heard it without cutting
in; later interruptions are not disclosure interruptions until it is spoken again. Two new tests: the
scenario fails on the previous commit; a guard shows a repeated disclosure can still be talked over.
Suite: 1266 passed.

**The greeting phase ends when the candidate agrees, not at 60 seconds.** Phases were clock-only, so
the briefing sent the moment consent was given said "Phase: greeting. Goal right now: Disclose AI,
get recording consent", on every call: the model's first turn was pointed back at a gate fixed lines
had already handled. Once consent is granted the engine now reports the next phase, and the interview
syncs its phase at that moment so the first answer does not read as a phase change and send a second
briefing. Three new tests; the two about consent and the double briefing fail on the previous commit.
Suite: 1264 passed.

**The answer to "are you an AI?" is not carried as the last question.** Asked mid-answer, the fixed
reply became the interviewer's last line in the rollover seed, so a fresh session was told "Yes, I
am an AI interviewer" and never learned which question was still pending. It is now an interjection,
like the silence nudge. Scoring already paired correctly here, and before consent the reply is always
followed by the consent question, so nothing else changes. One new test, failing on the previous
commit. Suite: 1261 passed.

**A request to stop or to speak to a person is not scored as an answer.** The pairing step matched
it with the question before it, so a model judge was shown "What tradeoff did you accept?" answered
by "I'd rather speak to a person" in every dimension prompt, and a low score quoting it passed the
quote check because the quote was exact. The pairing now skips turns the interview itself treats as
a stop or a human request, and such a citation voids the score as unfound. The rule was checked
against technical answers that mention stopping or a person ("we decided to stop the rollout", "I
asked a person on the SRE team"): none matched. Two new tests, failing on the previous commit.
Suite: 1260 passed.

**What is said in the last seconds before the goodbye stays on the record.** A regression from the
goodbye below: starting it six seconds early turned the limit into a window, and anything arriving
in it closed the call before it was looked at. Measured on the previous commit, the candidate's
last answer was missing from the transcript; "can you stop the recording?" and "I'd rather speak
to a person" ended as "time limit reached" with no flag; a prohibited question from the agent was
not flagged. The closing path now records the turn first, ends a stop or a human request under its
own reason and line with its flag, and flags a prohibited question it spoke over. Four new tests,
all failing on the previous commit. Suite: 1258 passed.

**The time limit ends an interview with a goodbye, within the limit.** At the limit the interview
only ended the call: no closing words, mid-sentence if the agent was answering the candidate's own
closing question. On the old interview, a candidate asking "so what is the team like?" three seconds
before the limit got the wrap-up line again and then the call dropped.

A consented interview now hears a short goodbye ("We're out of time. Thank you for talking with me
today."), started six seconds before the limit so it has played by then rather than running past it.
The limit itself stays a silent backstop. Saying a line cancels a reply in flight in both the client
and the runtime, so the goodbye replaces a cut-off sentence rather than talking over it. A call that
never became an interview ends as before, and a test pins that the silent-candidate call still ends
by the limit. One existing test expected nothing but the end at 899.9 seconds; it now expects the
goodbye at the new time. On the old interview the goodbye test failed as described.

**The frame loop counts slow control operations, not only slow steps.** The loop exists partly to
make the frame budget visible: a model step over 80 ms becomes queue debt that delays everything
after it, so over-budget steps are counted. But control operations run on the same serialized loop
untimed: accepting a turn, speaking a fixed line, and injecting context, which is every briefing and
every rollover seed of hundreds of tokens. On the real model those are prefills, and the seed is
likely the largest single stall of a call. Shown on the old loop: after a 400 ms steer, five frames'
worth of debt, the summary read "over_budget=0".

Control operations are now timed. Those over a frame's budget are counted separately, and the slowest
kind is named in the session summary the runtime logs at the end ("control_over_budget=1
control_max=400.0ms(steer)"). Steps and their counters are unchanged. The new tests failed on the old
loop only because the counter did not exist, so the evidence is the old summary above.

**A connect that times out fails on time and leaves nothing behind.** A regression from the previous
entry. When the runtime accepted the connection but never completed the handshake, the link timed out
and closed itself. The graceful close introduced there has nothing to close when the connection never
opened, so it only waited: with a 0.3 s timeout the error arrived after 2.3 s. Worse, the connect
attempt kept running. Verified against the stand-in: once the "runtime" came up after the timeout, the
orphaned attempt connected, and on the real runtime it would take the one conversation it serves from
every caller after it. The close it replaced stopped the event loop, which killed the attempt, so both
problems were introduced by that entry.

`close()` now cancels the attempt when the link never connected, and closes gracefully only when it
did. The error message also gives the real timeout ("after 0.3s", where it rounded to "after 0s"). Tests
also now cover a refused connection and a malformed message from the runtime, both already handled
correctly. On the previous link the timeout test failed, and the late connect was confirmed separately.

**Closing the client's real connection sends what was queued, closes it properly, and waits.** The
client's websocket link had no tests: its docstring said it needed the runtime on the other end, and
the websocket library is not installed here. Tested against a stand-in for the library, `close()`
stopped the link's event loop outright. Three audio frames and the session's final stop, queued just
before, never left. The connection was abandoned rather than closed, so the runtime would see an
abrupt disconnect instead of the end of a session. And `close()` returned at once, so a rollover
opened the next connection while this one was still open, on a runtime that serves one conversation
at a time and refuses a second as busy.

`close()` now asks the link's own loop to wait, up to a second, for the queue to empty, closes the
connection, and waits up to two seconds for the link to finish. On the old link the three tests for
those failed; nothing sent after close, a repeated close, and a connection the runtime ends marking
the link closed passed on both. The stand-in exercises the thread, the queue and the close, not the
wire itself; that still needs the real library and a runtime, which is a dependency to install on
your say.

**`--allow-silence` works on the box.** The runtime's opt-in fallback to the silent stand-in covered a
missing GPU only. On the GB10 there is a GPU, so the real model was chosen, and its load fails until
the weights are in place and the checkpoint-specific seams are wired. Simulated with a GPU present
and no weights: the runtime refused to start even with `--allow-silence`, so the plumbing could not
be run end to end on the one machine it matters most on. A model that cannot be loaded now falls back
too, still only with the flag, and logged as an error that says it is serving silence and is not an
interview. Without the flag a load failure stays fatal, which keeps the reason the fallback was made
opt-in. On the old server the fallback test failed; the fatal-without-the-flag guard passed on both.

**The driving contract is written where a driver will read it.** Several recent entries ended with a
note for whoever integrates the media gateway: call `tick` on every frame, wait for both sides to be
quiet before a rollover and rebuild its seed then, call `Interview.report()` at the end. Those notes
lived in this log and nowhere in the code. The `Interview` docstring still said only "feed it
backend events, perform the actions it returns", and the `Rollover` docstring still said to swap at
the turn boundary, which is the behaviour that cut speakers off. Both now state the contract, each
point noting the bug it prevents, with `InterviewRunner` named as the reference for the first four
and the demo's `report_for` for the fifth. Documentation only; no behaviour changed.

**Every way of driving a call produces the same report.** The scoring window and the report's flags
were assembled beside the runner and the demo only. The media gateway will drive an `Interview`
directly, and all it had was `transcript_for_scoring()`, which returns everything. Scoring that, the
obvious thing to do, scored the consent answer as interview evidence and dropped every compliance
flag: a candidate who talked over the disclosure, the incomplete-call flag, backend errors.

Report assembly now lives in one module, `zeg/report.py`. The demo's `report_for` and the runner's
window delegate to it, and `Interview.report()` builds the same report from the interview's own
record, taking any errors the driver saw. A test runs one mock call and checks the runner's report
and the interview's are identical. `transcript_for_scoring()` keeps its behaviour, and its docstring
now says not to score it directly.

One existing test checked the demo's source for the literal text `window=result.interview_window`,
which fails on how code is written rather than what it does. It now checks behaviour: through the
demo's report, a consent answer containing evidence is not scored. Scored without a window, the same
call does count it, so the test can tell the difference.

**A nudge is not mistaken for the question being answered.** The silence nudge added in the previous
entry is an agent line, and two places took the last agent line as the question. After "What did you
personally do on that project?", then "Take your time...", then "I wrote the advisory lock fix
myself", the report paired the answer with the nudge as its question, and a rollover seed told the
fresh session the nudge was the last thing asked. Both now skip known interjections when deciding
what the question was.

The rule is a closed list of interjections, which today holds only the nudge, not "a line without a
question mark". Prompts are often imperative, "Tell me about the rollout instead.", and a test pins
that such a line still replaces an unanswered question. On the old code both nudge tests failed and
that guard passed.

**A candidate who goes quiet after a question is not left in silence.** The call config had three
silence settings, a nudge at 4 s, a rephrase at 8 s and a move-on at 15 s, and nothing used any of
them. The model only speaks in reply to a finished caller turn, so a candidate who went quiet after
the agent's question got silence back. Measured on the interview: no action at all for over twelve
minutes, until the wrap-up.

Silence after a question now gets a fixed nudge at 4 s ("Take your time. If it helps, I can ask about
something else."), then, if it goes on, a move-on at 15 s that carries a question of its own, since
moving on to nothing leaves the candidate in the same silence. The engine abandons the unanswered
follow-up so the next answer starts a new thread; that is not recorded as a stalled ladder, which
means two general answers. Each line is said once per silence, and only after consent, before the
wrap-up, and when the agent spoke last. After the candidate, the silence is the model's to fill.

The rephrase setting is still unused, and deliberately: rephrasing a question the model asked needs
the model to generate it, and a fixed line cannot. On the old interview the nudge and move-on tests
failed; the three guards passed.

**Calls shorter than fifteen minutes wrap up and move through every phase.** Calls run "up to"
fifteen minutes, but the wrap-up time was a fixed 810 seconds and the phase plan was written in
absolute seconds for a fifteen-minute call. Measured: a ten-minute call was due to wrap up after it
had already ended, so a silent candidate was never told the interview was closing and the call
simply stopped; it also never reached the scenario or close phases. A five-minute call never left
the first depth phase, so every briefing near its end named the wrong phase and the wrong goal. The
only test for a shorter call passed an explicit wrap-up time and so never exercised the default.

The wrap-up now defaults to ninety seconds before the end, never before three quarters of the call:
810 of 900, 510 of 600, 225 of 300. An explicit value is kept. The default plan is fitted to the
call, with every phase before the close ending where the wrap-up starts and the close ending with the
call; for fifteen minutes it is exactly the plan as written. On the old code six of the new tests
failed; the fifteen-minute cases and the explicit override passed on both.

**Making room for a fixed line is not reported as the candidate interrupting.** The previous entry
had the runtime cancel an open reply when a fixed line arrives, and it used the reason
"superseded", which already meant a new caller turn had begun. The client reports a cancellation it
did not start as an interruption, and the interview counts "superseded" as the candidate's doing.
Traced end to end: the runtime's cancel reached the client as an interruption, and before consent
the interview flagged "The candidate talked over the recording disclosure" and repeated it, when
nobody had said a word. That entry introduced the path.

The runtime now uses its own reason, `replaced_by_fixed_line`, and the client stops that reply
locally without reporting it, the same as when the client replaces a reply itself. Its audio is still
dropped. Against the old client the end-to-end test failed with the flag present; against the old
server session the cancel carried "superseded".

**A fixed line never merges into the model's half-finished reply.** Before speaking a fixed line,
such as the wrap-up or a redirect, the client cancels the model's reply, but only a reply it has
heard about. A reply the runtime had opened a moment earlier was left running. The runtime then
ignored the fixed line's own open, because a response was already open, and the two merged.
Measured on the server session: "Tell me more about That is about all the time I have.", one
completed response. The candidate hears a sentence run straight into the wrap-up, and the transcript
records that merged line alongside the fixed line the interview already recorded. The runtime now
cancels an open reply itself when a fixed line arrives, so the fixed line gets its own response
whatever the client knew. A fixed line with nothing open is unchanged. On the old server session the
race test failed.

**The record says who cut the disclosure off.** Before consent, the interview treated any report of
the agent being interrupted as the candidate talking over the recording disclosure. It repeated the
disclosure, which is right whatever the cause, and flagged "The candidate talked over the recording
disclosure". Measured: an interruption with the reason "no_progress" or "trailing_silence", a
runtime stopping a stalled response, produced exactly that flag. A compliance record that blames the
candidate for something the system did is wrong.

Our own runtime reports its stalls as a finished response rather than a cancellation, so today this
reaches the interview only through the backend contract, which allows it and whose client test
relays exactly that. The interview now keeps the reason. A barge-in, or a response superseded
because the candidate began a new turn, keeps the old wording. Anything else is recorded as cut off
by the system, not the candidate. The disclosure is repeated either way. On the old interview the
three system-reason tests failed and the two candidate-reason tests passed.

**A barge-in cancels the response the candidate is hearing, not whichever is current.** The cancel
message carried only a reason, and the runtime cancelled whatever response was open. The client
plays agent audio out at speaking pace, so the runtime can finish generating a response while the
candidate is still hearing it and open the next one. A candidate talking over the tail of the first
then cancelled the second, which could be a fixed line the interview had just asked for, such as the
wrap-up or the redirect over a prohibited question. The client now remembers the response whose
audio is queued or playing and names it in the cancel, and the runtime ignores a cancel for a
response that has already ended. A cancel with no id behaves as before, so nothing else had to
change at once. Against the old runtime session the stale-cancel test failed, and against the old
client the cancel carried no response id at all.

**The codec pipeline serves more than one response.** The runtime decodes codec tokens one frame
behind the model so the decode cost hides under the next step, and `flush()` drains the last frame
at the end of a response. Whether to decode on `submit` was decided by a "started" flag, and it
stayed set after `flush()` had emptied the pipeline. So the first frame of the next response asked
the codec to decode None. Reproduced with a codec that rejects None: the first response was fine and
the second raised. On the box that is the model step failing, and the session dying, at the start of
the agent's second reply. Every existing test covered a single response. `submit` now decodes only
what is actually in flight, so each response starts one frame behind cleanly. On the old decoder the
new two-response test raised exactly that error.

**Clefts, passives, spoken quantities, named costs and hands-on debugging now count.** Twelve of
sixteen further ordinary phrasings were not recognised: "It was me who rewrote the worker", "I'm
the one who rewrote it", "The worker was rewritten by me"; "twice a week", "half the batches",
"tenfold"; "The cost was parallel reconciliation", "the catch was", "on the flip side"; "I dug into
the logs", "stepped through it in a debugger", "looked at the logs", "set a breakpoint". A few that
did count did so by accident, through another number in the same sentence.

Each is tied to the thing that makes it evidence, so the lookalikes stay out: "the second half of
the call" is not a quantity, "the cost of living" and "I accepted the cost estimate" are not a price
paid, "dug into the feature backlog" and "looked at the design doc" are not debugging, and "it was
the platform team who rewrote it" is not ownership. On the old scorer all fourteen positive tests
failed and the six lookalikes passed.

**Lean matched pairs found two more ways the scorer marked down how someone speaks.** The
matched pairs carry several markers per dimension and a score caps at two, so a variant losing
one could hide. Delivery variants run over the recognition eval's one-marker transcript instead.
Filler, hedging and both tenses held there, confirming earlier fixes. Two did not.

Non-native grammar: "I am rewrite the settlement worker" lost ownership, and "First is the lock,
after is the backfill" lost communication. A dropped pronoun: "Rewrote the settlement worker
myself", common in terse speech and from speakers of languages that drop subject pronouns, lost
ownership. "I am", "I'm" and "I was" may now come before the verb, and "after is", "after this"
and "afterwards" count as sequence words; a bare "after" does not, since "the first alert came
after the deploy" is about time.

The dropped pronoun needed a judgement. A verb with no subject is as often "we" as "I", and
crediting every one made "Isolated it to one merchant", said of a team, score higher than "We
isolated it". So it counts only when the sentence says whose work it was: "myself" in it, or
opening with "personally". Past forms only, never followed by "by", and "Found out later", "Ran
into a deadlock", "Led to duplicate payments" and "Fixed income trades" stay out. Both pairs join
the bias eval. On the old scorer nine tests failed, including both pairs; the negatives passed.

**The recognition eval can now see a single lost signal.** Its transcript carried several markers
for every dimension, so a degradation that destroyed one could never move a score. That is why the
hyphenated-compounds degradation held even on the scorer that could not read "gave-up": the same
answer also said "doubled". A second transcript now carries exactly one marker per dimension,
and a test pins that property so it cannot drift. Run against the scorer from before the spelling
fix, hyphenated compounds took tradeoffs on it from 3 to nothing, and that test fails there as it
should; every other degradation held. On the current scorer every degradation holds on both
transcripts.

**How a recogniser spelled a compound word no longer decides the score.** Recognisers write the
same compound three ways: "trade off", "tradeoff", "trade-off". The scorer's patterns matched one
spelling of each, and eight of sixteen spelling variants lost their evidence: "the trade off was",
"the root-cause was", "I re-wrote the reconciler", "I set-up the harness", "I rolled-out the fix",
"I ruled-out the network", "the flame-graph". A candidate has no say in which spelling the
machine picks.

Spelling is now normalised once, where every signal is read: a hyphen joining two words becomes a
space, and a split "re wrote" or "re built" is rejoined. The tradeoff pattern also takes "trade
off" with a space. Quotes in the report keep the candidate's own words. On the old scorer nine
spelling tests failed.

The recognition eval gains a hyphenated-compounds degradation, since its docstring promised
variations it never tested. Honestly, that degradation held on the old scorer too: the clean
transcript's cost answer also says "roughly doubled", so losing "gave-up" did not move the score.
It exercises the path; the unit tests are the proof.

**The recognition eval compares every dimension and cannot pass on nothing.** The recognition
eval scores the same answers clean and degraded the way a recogniser degrades them. It had both
blind spots the matched-pair eval had. A degradation "held" if the overall score and band
matched, never the dimension scores, which is how filler costing ownership went unseen there.
And a judge that scored nothing was reported as held, "recognition quality does not move the
score", because nothing equals nothing: measured on the old instrument, held was True for a judge
that never produced a score. A degradation now holds only if every dimension matches, a result
with nothing on either side is void and the verdict inconclusive, and any dimension that moved is
named. Run dimension by dimension, all five degradations still hold on the current judge, so this
guards against a future regression rather than fixing a live one. On the old instrument the
no-score test failed on its assertion; the moved-dimension test failed only because the field did
not exist.

**Scoring pairs an answer with its question even when the candidate asked something first.** The
scorer pairs each interviewer question with the next thing the candidate says. After "What did you
personally do on that project?", a candidate who asked "Sorry, can you tell me more about the role
first?" had that recorded as the answer, and their real answer, "I wrote the advisory lock fix
myself", was then paired with the interviewer's explanation of the team as its question. The
heuristic judge mostly reads answers, so its numbers barely moved, but a model judge is shown the
pairs. A candidate's question is now skipped when pairing, the way a hesitation already was, using
the same rule the interview applies live, so an answer that carries evidence ("we cut p99 from
400ms to 30ms, right?") still pairs as an answer. On the old scorer the pairing test failed.

**A candidate's question is not probed as if it were a claim.** Mid-interview, a question from the
candidate reached the engine as an ordinary answer. Measured: "Sorry, what does this team actually
work on day to day?", "How does the team split on-call" and "Can you tell me more about the role
first?" each became a claim, and the engine told the model to "Ask for what they personally did, as
opposed to the team" about the candidate's own question.

A question now holds the ladder the way a hesitation does: it is recorded, it starts no claim and
issues no probe, and the model answers it. Detection is conservative. A turn is a question if it
ends with a question mark or opens with a question form, allowing a leading "sorry," or "so", and
only if it carries none of the scorer's evidence markers, so "we cut p99 from 400ms to 30ms, right?"
stays an answer. "What I did was rewrite the reconciler" is not a question form and stays a claim.
On the old interview the three question tests failed and both guards passed.

**"My part was the fix" counts as ownership.** Asked what they personally did, people answer as
often with a possessive as with "I did". None of nine possessive phrasings counted: "My part was
the advisory-lock fix", "The advisory lock was my change", "That fix was mine", "I was in charge
of the rollout", "I took ownership of the reconciler". A new matched pair, the same facts with
ownership claimed that way, scored ownership as nothing against 4.

The ownership pattern now recognises a claimed part or role, something being "my change", "my
responsibility" or "mine", being in charge, and taking something on or over. Narrow on purpose,
because "my" is everywhere: "My job is at a payments company", "That was my manager's call", "It
was my first job" and "Our team's part was the migration" are not claims and stay out. On the old
scorer ten tests failed, including the new pair; the negatives passed on both.

**Tense no longer decides a score.** The judge's word lists were past tense. Two new matched
pairs say the same past work in other tenses. Present perfect ("I've written the fix", "I've
reproduced it") scored ownership as nothing, against 4 in the past tense. The historical present
("I write the fix", "I reproduce it", "we give up parallelism, batch time doubles"), which is
especially common in non-native speech, lost ownership and tradeoffs entirely. The existing
non-native pair kept its key verbs in the past tense, so it could not have caught this.

Ownership verbs are now generated in every tense from a short table, and "I've", "I have" and "I
had" may come before the verb. "I'd" may not, since "I'd rewrite it differently" is not a claim
of having done it, and a few base forms are left out on purpose: "I find it hard", "I run into
this" and "I drive to work" are not claims either. Tradeoff, debugging, causal and number lists
take the present forms too. "Trades" alone is not a tradeoff, because in a payments interview "we
reconcile trades nightly" is ordinary. On the old scorer both new pairs failed and eleven tests
failed in all.

**The bias eval now has a vocabulary pair, and it found one more inconsistency on arrival.** The
recent word-list fixes to the judge were each checked on their own, and nothing in the
matched-pair eval would have caught them coming back. The new pair says the same facts once in
the classic words and once in equally ordinary ones: "I personally implemented" for "I wrote",
"the reason was" for "because", "I isolated it" for "I reproduced it", "the tradeoff was" for
"we gave up".

Scored dimension by dimension before it was committed, it was not clean: ownership 4 against 3.
"I reproduced it" counted as ownership and "I isolated it" did not, though both are first-person
investigative work and both already counted as debugging. The ownership verbs now include the
investigative ones the list was missing (isolated, narrowed, ruled out, bisected, measured),
consistent with reproduced, traced and diagnosed already being there.

Run against the scorer from before the vocabulary fixes, the same pair scored 8/10 as written
and no score at all in the variant, with ownership, debugging and communication all unscored: a
candidate sent to a human screen for their choice of words. That is the class of defect the pair
now guards. Tradeoffs did not move in that run only because both halves also say "doubled".

**The bias eval compares every dimension, and it found filler costing a candidate ownership.**
The matched-pair eval, which says the same substance twice with only the delivery changed,
counted a pair clean when the overall score and band matched. It never compared the dimension
scores, which are what the report shows. Run dimension by dimension, the verbal-filler pair was
not clean: ownership was 4 in the plain half and 3 in the half with "um" and "you know", while
the overall rounded to 8 on both, and the suite reported "no measurable difference".

The cause was the filler stripper. It removed "um," but left the comma before it, so "I, um,
reproduced it" became "I, reproduced it", and the comma between the pronoun and the verb broke
ownership. Filler correlates with nervousness and with speaking a second language, which is
exactly what this eval exists to protect. The stripper now takes the preceding comma with the
filler, and a pair is clean only if every dimension matches; the report names any dimension
that moved. With the new eval and the old stripper, the three existing bias tests fail with
"ownership moved: 4 vs 3". With both changes all pass.

A correction to earlier entries: several recent scoring changes cited "the matched-pair evals
are unchanged" as evidence. That was true, but it was weaker evidence than it sounded, because
the eval could not see a dimension moving. The next thing is a vocabulary pair, the same facts
in different ordinary verbs, so the word-list fixes above are guarded by the eval too.

**The real client refuses audio frames of the wrong length, instead of mistiming every turn.**
It checked each frame's sample rate but not its length, and every caller-side timing counts
frames and assumes each is 20 ms: the endpoint, the barge-in threshold, the watchdog, and the
pacing of the agent's own audio, played out one frame per caller frame. Measured against a
640 ms endpoint: with 10 ms frames a turn ended after 320 ms of silence, shorter than a breath;
with 40 ms frames, after 1280 ms. Nothing reported a problem. A frame that is not the configured
length is now refused with a message naming what was expected, the same way a wrong sample rate
already was.

Measuring time from each frame's real length instead would also have to change playback pacing,
which is a larger change than the problem warrants while the contract is 20 ms. The gateway's
framer already cuts audio to the shared 20 ms constant, so this matches what integration sends,
and any future drift becomes an immediate error rather than halved timings. On the old client
both new tests failed.

**A DC offset on the line no longer reads as someone talking.** Every turn start, turn end and
barge-in decision rests on one loudness measure, `rms`, and it squared the raw samples, so a
constant bias counted as sound. Capture paths often carry one: the signal sits slightly off zero
even in silence. Measured: an offset of 700, about 2% of full scale, crossed the speech
threshold. Driven through the real client, a candidate who stopped talking on such a line was
still "speaking" three seconds later: the turn never ended, so the model never got a finished
turn to answer, and on a real call a silent line would also keep barging in on the agent.
Loudness is now measured about the frame's own mean. Speech is zero-mean, so for real audio it
measures what it always did: an offset added to a tone leaves its loudness within 0.002. On the
old code all three new tests failed. The gateway uses the same module and its tests still pass.

**A report says which judge produced it, and a heuristic one says not to use it.** The
heuristic judge's own documentation says a report from it "should never be shown to a hiring
manager": it matches wording and cannot tell a correct explanation from a confident wrong one.
But the report did not record or show which judge produced it, and the demo always uses the
heuristic judge, so "9/10 — advance" from it looked exactly like a real assessment and the
warning never reached anyone reading one. The report now records its judge. A heuristic report
carries a line under the headline saying it matches wording rather than judging answers and is
for testing only, not for a hiring decision; any other judge is named. Every demo report now
shows that line, which is intended. On the old code all three new tests failed.

**The judge's record says what actually went wrong with a score.** Two different failures were
recorded as one. A score with no quote at all was counted as a fabrication and described as
having "cited a quote not present in the transcript", when nothing had been cited. And a quote
taken from the interviewer's question got the same description, though it is in the transcript,
just not in anything the candidate said. Both scores are still voided: evidence or it did not
happen. But a score given without a citation is now recorded separately as uncited, with a note
saying so, and a quote that is not in the candidate's answers is described as exactly that. The
fabrication count now counts only fabrications. On the old code the two new tests failed; the
existing fabrication test failed too, but only because its expected wording changed.

**A judge's score is taken only as the whole number it gave.** The score went through `int()`.
In Python that turns `true` into 1, so a boolean became a real score at the bottom of the
rubric, and it truncates 3.9 to 3 and 2.5 to 2, each a number the model never gave. `false`
was rejected only by coincidence, because it becomes 0, below the scale, and the string "3.5"
was rejected while the number 2.5 was accepted. A score is now accepted only if it is a whole
number, however it is written (3, 3.0, "3"); booleans and fractions are unreadable, like any
other malformed verdict. On the old code exactly the three from the diagnostic failed.

**A judge's verdict survives other braces in its reply.** The parser took everything from the
first `{` to the last `}` and parsed that. Any other brace in the reply widened the span, so a
good verdict followed by a note such as "(I ignored the {placeholder} in the brief.)" was thrown
away as unreadable, and so was the same verdict given twice. The parser now decodes every
complete JSON object in the reply and keeps the ones that are verdicts.

Where the reply holds two different verdicts, it refuses. Taking the first or the last would be
guessing which one the model meant, and the parser's own rule is that a guess becomes a number in
a hiring report. The old parser also rejected that case, but only by accident, because the span
across both objects was not valid JSON; now it is a stated rule with its own test. On the old code
two of the four new tests failed; the other two, braces inside a quote and conflicting verdicts,
passed there as well.

**The judge's prompt asks for what its guard accepts.** Two mismatches between the model judge's
prompt and the check on its quotes. The prompt asked for "a verbatim span from the transcript",
and the transcript it is shown includes the interviewer's lines, but the guard has only accepted
the candidate's own words since the fix that stopped a judge citing the interviewer. So a model
following its instructions exactly could quote a question and have a valid score voided and
recorded as a fabrication. The prompt now says to quote only from the candidate's lines, and
that the interviewer's words are never evidence about the candidate.

Second, every answer is shown to the judge as "Candidate: ...". A quote copied with that label
failed the verbatim check, because the label is not in the answer text, so a genuine quote and
its score were voided over formatting. A leading "Candidate:" label is now stripped before the
check. An "Interviewer:" label is not, and such a quote is still rejected. On the old code the
label test failed; the prompt test failed because the guidance was not there. That test only
pins the prompt's wording: whether a real model follows it needs a model on the box.

**The live engine and the scorer agree on what a specific answer is.** The engine decides during
the call whether an answer was specific, and two general answers in a row abandon the thread with
"Change topic". It used its own list of five causal words plus a number check. The scorer's lists
have since been widened, so the two disagreed. Measured: two answers, "there were a lot of things
going on, and the lock expiring early caused the double settlements" and "basically the reason was
a missing unique constraint", each scored as technical depth and communication afterwards, and the
engine called both vague and told the model to change topic on a candidate who had just explained
the root cause twice.

The engine now asks the scorer's `signals()`, the same way live evidence already did, so the call
cannot drop a thread the report would credit. Two answers with nothing in them still stall the
ladder. The first version of one new test used an answer with no vagueness word in it, so neither
engine would ever call it vague and it passed on the old code as well; it now carries both a
vagueness word and an explanation, and fails on the old engine as it should.

**Explanations and structure count, in ordinary phrasing.** The last two dimensions with short
lists. Of ten ordinary causal explanations, three were recognised: "which caused the double
settlements", "as a result", "the reason was", "that is why" and "the problem was that" counted
for nothing, and "led to" and "since" scored technical depth only because those answers happened
to contain a number. Communication was worse. Its brief is structure and responsiveness, but only
causal words were ever checked, so none of five structured answers counted: not "first we
reproduced it, then we added the lock, and finally we backfilled", not "there were two parts to
it", not "to answer your question directly".

The causal list now covers the ordinary phrasings, and communication also recognises a sequence,
a count of parts, and a direct answer given first. "Since" is left out on purpose: "since March"
is about time, and a word that means cause half the time is not evidence of it. A single "then"
or "the first release" is not structure. On the old judge eleven of the new tests failed; the
matched-pair and band-spread evals are unchanged.

This finishes the pass through the heuristic judge's word lists. All five dimensions were
recognising a narrow vocabulary, which scores how a candidate talks rather than what they did.

**Tradeoffs and debugging are recognised in the words people actually use.** The same gap as
ownership, in the two other dimensions with short word lists. Of ten ordinary answers to the
engine's own tradeoff probe, three were recognised; the list did not contain the word
"tradeoff", so "the tradeoff was extra operational complexity" counted as nothing, and nor did
"we sacrificed strict ordering", "we chose consistency over availability" or "in exchange we lost
parallel batches". Of ten debugging answers, four were: "I ruled out the network", "I isolated it
to the settlement worker", "I added logging and found two workers taking the same batch" and "I
traced one request through all three services" all counted for nothing.

Both lists now cover the ordinary phrasings, anchored so that "I accepted the offer", "we chose
Postgres", "the profile page" and "I added a feature flag" stay what they are. One phrasing was
left out on purpose: "it made deploys riskier but the fix was worth it" names a cost only by
implication, and rewarding "worth it" would reward a phrase rather than a cost. On the old judge
twelve of the new tests failed.

The report-excerpt test changed its expected quote for debugging: the window sits on the first
marker the judge matches, and "could reproduce it in staging" is now one, ahead of "I suspected
the retry path". The quote still shows debugging evidence, just the earlier of two.

**Ownership is recognised in the words people actually use.** The heuristic judge counted
ownership only when "I" was immediately followed by one of ten verbs. Of twelve first-person
claims of ownership, it recognised two. "I personally rewrote the reconciler", which is the
natural answer to the engine's own probe for what the candidate personally did, counted as no
ownership at all, and so did "I implemented", "I added", "I refactored", "I migrated", "I then
fixed" and "I was the one who wrote". Two candidates claiming the same work in different words
scored differently: that is scoring vocabulary, not ownership, and it is exactly what the
matched-pair evals are meant to rule out.

The judge now allows up to two ordinary words between "I" and the verb ("personally",
"actually", "then"), knows the verbs engineers use, and recognises "I was the one who" and "I
was responsible for". "Basically" is deliberately not allowed in between, since it is on the
vagueness list. The negative cases stay negative: "we wrote it", "the team implemented it and I
watched", "I think the platform team built it". On the old judge twelve of the new tests failed;
the matched-pair bias evals are unchanged.

**A follow-up ladder no longer keeps a session past the model's window.** The rollover policy
never rolls while a probe ladder is descending, so the thread is not dropped. But a candidate
giving long, specific answers keeps the ladder going, and nothing overrode the rule. Measured
on a mock interview: sessions lived 246 and 227 seconds, against a model that holds about 120.
The thread the rule was protecting had already fallen out of the model's context, which is
the failure rollover exists to prevent.

The policy now has a hard horizon (110 s). Past it, it rolls at the next turn boundary even
mid-ladder. Rolling mid-ladder loses less than it used to: the engine keeps the ladder state,
and the seed carries the live claim with the answers under it. The same interview now peaks
at 137 s with 40-second answers and 121 s with 15-second ones. The remaining overshoot is one
answer long, because a switch waits for the candidate to finish, which is right.

Two existing tests had encoded the bug: both checked that a ladder held a session aged 200
seconds. They keep their intent at ages inside the window, between the soft and hard
horizons, where the ladder still holds. On the old policy the runner test failed at 245.8 s;
the other new tests failed there only because the setting did not exist.

**"I'd rather speak to a person" is answered, and so is "are you a real person?"** Both were
left to the system prompt, which is a request rather than a requirement, and both were
treated as ordinary answers mid-interview. Measured: asked "I'd rather speak to a person",
the interview issued its next probe — the candidate asked to be taken off the call and was
asked what they personally built. The disclosure offers a human in the first sentence of the
call, so that is a promise the agent broke while the candidate was still on the line.

A request for a person now ends the call with a fixed line, flagged with the time for
whoever picks it up. A question about what the agent is gets the honest answer immediately,
and the interview carries on: it is a question, not an answer, so it starts no claim and
moves no ladder, which it used to do.

Both matchers are narrow, and the negative cases are the point again: "we talk to the
payments team every week", "I spoke to the on-call engineer and we rolled it back", "you can
talk to the API directly" are answers, not requests. On the old code three of the four tests
failed; the guard passed.

**A question at the consent gate gets an answer, not a hang-up.** The gate wanted a clear
yes and treated everything else as refusal, including questions. Measured: "What happens to
the recording?", "Are you a real person?", "Sorry, could you repeat that?", "Does it have to
be recorded?" and "Who gets to see this?" each ended the call, and each candidate heard "That
is completely fine", the line written for a refusal, in answer to a refusal they had not
made. Five reasonable questions, five lost candidates.

Four kinds are now recognised and answered, and the consent request comes again in the same
breath: what happens to the recording, whether the agent is a person, whether the recording
is required, and a request to repeat (which gets the disclosure again, since it ends with
the question anyway). One utterance, not two, because saying a line cancels whatever the
agent is saying and a separate re-ask would cut off the answer it follows.

What the answers say is limited to what is actually known. The recording answer says a human
reviewer goes through it and offers to have the team confirm storage and retention, rather
than inventing a policy. Only these four kinds are recognised; anything else falls through
to the gate, because an agent improvising about a recording is worse than one handing the
call to a person.

The gate itself is unchanged: silence is still not agreement, a hedge is still not a yes. A
reply that refuses and asks in the same breath ("no, what happens to the recording?") goes
straight to the decline, because answering and asking again would be pressing somebody who
has said no. Capped at two questions. On the old interview the four behavioural tests failed
and the three guards passed.

**A candidate who asks to stop is heard, mid-interview.** Consent was a gate passed once at
the start. After that, "actually, can you stop the recording?" was treated as any other
answer: the interview asked its next question and the call carried on recording, which is
the one thing the consent gate exists to prevent. Any such answer now ends the call with a
fixed line, and the record carries a flag with the time it happened and says a human must
decide whether what was recorded before may be used. That decision is not one to make in
code.

Detection is deliberately narrow, because this runs on every answer in a technical
interview. The false-positive list is as much the point as the withdrawals: "we stopped the
retries", "we had to cancel the call to the payments API", "the consumer stops recording
metrics", "I want to stop guessing and actually measure it". The first draft ended the
interview on the last two, which its own tests caught: a stop has to have no object behind
it, and the interview is not something you cancel *to* anything. On the old interview the
two behavioural tests failed and both guards passed.

Open, for a human: whether a withdrawal should also stop the earlier part of the call being
scored. The report flags it and scores what was there; making that call in code would be
deciding a legal question.

**A subject the agent was pulled off stays off, across sessions.** The briefing that comes
with a redirect lives in the session that was told it. A rollover opens a fresh session every
hundred seconds, and its seed carries the engine's briefing and the last exchange, so the
instruction went with the old session: printed from the old code, the seed a fresh session
would get right after "are you married?" was refused mentions the subject nowhere. It holds
the redirect line as "the last thing said" and nothing else. The next session starts from the
same system prompt the model has already ignored once.

The engine now records each refused subject and names them in every briefing ("Never ask
about: family, salary history."), which is what a rollover seed is built from, so the
instruction outlives the session. Recorded once per subject and kept for the rest of the
call. This is a new capability rather than a corrected misbehaviour: on the old code the two
tests fail because the method did not exist, and the demonstration above is the actual gap.

**The model is told why it was interrupted, and the flag claims only what is known.** Two
things were wrong with cutting off a prohibited question. The flag said the question "was
cut off", which is a stronger claim than we can make: saying a line cancels the model's
reply, but how much the candidate heard depends on how far ahead the audio was, and a
backend that reports a reply in one piece may report it only once it has been spoken. The
flag now says the question was asked and that a redirect was spoken over it, so the
candidate may have heard part of it. A compliance record that overstates what happened is
worse than one that is plain about the uncertainty.

The second thing: nothing told the model anything. The system prompt already forbids those
subjects and it asked anyway, so the standing instruction is not enough on its own, and the
next turn would likely be the same question again. A redirect now carries a briefing naming
the subject and saying never to return to it. On the old interview both new tests failed.

**A prohibited question from the model is cut off and put on the record.** The block list
gated only our own fixed lines. The model speaks for itself, so its questions arrive as
transcript text after the fact: fed "So before we go on, are you married?", the interview
recorded it as an ordinary agent turn, raised no flag and did nothing, even though the block
list recognises the phrase. The docstring claimed the check runs before synthesis, which was
true only for our lines.

The interview now watches the agent's own text as it streams and, on a match, speaks a fixed
redirect. Saying anything cancels the model's reply in the client, so the question is
interrupted rather than finished, and a flag names the category and the phrase. One redirect
per reply; the next reply is watched again. A false positive costs one changed subject,
which is the trade the block list was always written for.

What this does not do: the candidate has already heard however much was spoken before the
words reached us, and a backend that reports a reply only when it is finished can only be
cut off after the fact. Detection is a word list, so it catches phrasings it knows. On the
old interview four of the five new tests failed; the fifth, that an ordinary question is left
alone, passed on both.

**A report from a call that was cut short says so.** Every failure path now ends the call
with whatever was gathered, which is right: a candidate who answered twelve minutes of
questions should still be scoreable. But the report then reads exactly like one from a
complete interview. `report_for` now flags a call that had consent and never reached its
wrap-up, naming how it ended, and lists any errors from the call. Measured end to end with a
backend that refuses a second session: a 90 second call whose report previously said only
"Only 2 of 5 dimensions had citable evidence" now also says the interview is incomplete and
why. In that example the report was already "no score"; the case this really guards is a
longer truncated call, which scores normally and would otherwise look whole. A finished call
and a declined one are not flagged.

**The compliance flags reach the report.** The interview records them — a candidate who
talked over the recording disclosure, a prohibited question that was blocked — and the
report has a "Flags, for a human to weigh" section for exactly this. The demo printed them
as separate console lines and scored the call without them, so the report itself carried
none: composed the old way the same call produced `flags=[]` and no flags section at all.
The console is one view of a report; anything that keeps the report rather than the terminal
scrollback kept one that did not mention them. Report building is now one function,
`report_for`, which passes the interview's flags along with the interview window, and the
demo uses it. Scoring still adds its own flag about thin evidence, and the window still
decides what is scored.

**A rollover that cannot open a new session ends the call with the transcript intact.** The
old session is closed before the new one opens, on purpose, because the box runs one
conversation at a time. So a refused new session ends the call. It used to escape the runner
instead: the exception came out of `run()` and the whole interview went with it, transcript
and report included. That is reachable every hundred seconds of a long call, and more so
now that the runtime refuses connections when it has no usable model. The runner now records
the error, ends the call as a backend failure, and returns what was gathered. A rollover
that did not happen is not counted as one. On the old runner the new test failed with the
backend's exception coming out of the run.

**A dropped connection ends the call at once, and says so.** The client noticed a connection
that had gone only through its watchdog, which counts 200 caller frames: four seconds of a
candidate talking to nothing, reported afterwards as "the speech runtime went silent", which
sends whoever reads it looking at the model rather than at the connection. The client now
checks the link while draining messages and fails the call immediately with a message that
names the connection. Our own close is not reported as a drop. On the old client the new
test failed with no error raised at all; the guard passed on both.

This is the fourth fix in this run through the failure paths, and they line up: the runtime
keeps its weights across sessions, reports a model that dies mid-call, reports a session
that fails outright, and now the client reports a connection that goes away. All four
presented as silence with a misleading explanation.

**A session that fails outright says so instead of dropping the socket.** If anything in a
session raised rather than returning, the connection handler raised with it. Measured with a
model whose prefill fails: the client had been sent `session.ready` and nothing else, not
even `session.configured`, and nobody closed the socket, so it waited out its own watchdog
and reported the runtime as having gone quiet. Prefill is the likeliest first failure on the
box, because it is one of the seams that is not wired up yet. The handler now sends a fatal
`session_error` and closes the session with status failed before tearing down, on the normal
close code: a new close code would be a protocol change, and the message already says it.
Cancellation still propagates, and the server stays free to take the next call. On the old
server the new test failed with the model's own exception coming out of the handler.

**A model that dies on a commit or a fixed line tells the client.** The server noticed a
dead frame loop only where it drains frame results, so a failure was seen only if another
frame arrived after it. A model that raises on a commit, a steer or a fixed line produces no
frames at all. Measured with a model whose synthesis raises: the client received the
handshake and then nothing, for as long as the test was willing to wait. On the box the
candidate hears silence until the client's own watchdog fires four seconds later and
reports the runtime as having gone quiet, which is the wrong diagnosis; a slower variant
fills the queue and reports the model as being behind, which is also wrong.

The frame loop now takes an `on_error` callback, called on its own thread when it stops on
an exception, and the server wires it to wake the consumer, which already knows how to close
the session as `model_error`. The session is closed with status `failed` and that reason, so
the client and the transcript say what actually happened.

On the old runtime the server test failed for the right reason: the client was told nothing.
The loop test failed there only because the parameter did not exist yet, so it proves less.

**The runtime keeps its weights between sessions.** The server closed the model when a
connection ended. `close` releases the weights, `load` is documented as once per process,
and nothing reloads, so every session after the first got an unloaded model. On a long call
the second session is not an edge case: it is the first rollover, which is the whole memory
layer. The loopback tests never caught it because they wire a client session straight to a
server session and never go through the connection handler.

Closing was standing in for something real: `prefill` does not replay the backbone's
recurrent state, so without a reset the next caller would be talking into the previous
caller's conversation. The model interface now says that outright with `reset()`, "drop the
conversation, keep the weights". The stand-in implements it; on the real model it is SEAM 6,
unwired like the others, because clearing recurrent state is checkpoint-specific and cannot
be written blind. The server resets between connections, releases the model only when the
process stops (`RuntimeServer.close`), and if a reset ever fails it releases the model and
refuses further connections rather than hand the next candidate a model mid-conversation.

A new test file covers the connection lifecycle with a fake socket and a stub model. On the
old runtime all four failed, including the one that matters: the second connection never
stepped the model, because the weights had been released.

**A rollover waits for the agent to stop talking too, and its seed is built at that
moment.** The rollover already waited for the candidate's turn to close. It did not wait
for the agent. The runtime releases a turn's final transcript as the model opens its reply,
and that transcript is what asks for a rollover, so the session was closed mid-reply:
measured over the real client, server and wire, two of three closes happened with a response
in flight and four frames of agent audio still queued. The candidate hears the agent cut off,
and the fresh session, which answers only a finished caller turn, then waits in silence. The
backend contract gains `agent_speaking`, the companion to `caller_speaking`, defaulting to
False so nothing else has to change. The real client reports a response in flight or audio
queued; the mock reports its own playback. The runner holds the rollover until both are
quiet.

Because the roll now happens later than it is asked for, the seed is rebuilt at that moment
(`Interview.seed`), so it carries the question the agent has just asked. That exposed a gap
in the seed itself: `last_exchange` took only the caller replies after the last agent line,
so a seed built right after a question held the question and none of the candidate's words.
It now reaches back for the answer before the question when nothing has answered it yet, in
the order they were said. An existing test caught this, and it was a real regression rather
than a stale expectation.

On the old runner the full-stack test failed (two closes mid-reply). On the old memory layer
the new seed-shape test failed. The gateway's driver will want the same wait when the tracks
merge.

**A line the model never marks finished still reaches the transcript.** The runtime's
response watchdog closes a response that was audible and then quiet for about a second
("trailing silence"). That response has been heard. The model just never sent its own close.
The watchdog closed it with status `failed`, and the client records a response's text only
when its status is `completed`. So a line the candidate heard in full was missing from the
transcript, and with it from scoring, the engine's record of what was asked, and the rollover
seed. Trailing silence now closes as `completed`, still with the reason `trailing_silence`
and still cancelling the model. A response that made no progress at all is still `failed`.
On the old runtime both new tests failed: the server-session status test, and a test over
the real client, server and wire with a model stand-in that speaks a line and never closes
it.

**A vague phrase no longer marks down a specific answer.** The heuristic judge took a point
off every dimension when most answers contained a word from its vagueness list ("basically",
"things", "a lot of"), whatever else the answer said. The same five specific answers scored
9/10, advance, as given, and 6/10, advance with reservations, when each opened with "There
were a lot of things going on." Every dimension dropped a point on identical evidence. An
answer now counts as vague only if it also shows none of the judge's markers, which is how
the interview engine already judged vagueness live. Answers with nothing in them still cost
the point. On the old code the lead-in test failed and the content-free guard passed.

**No answer to the consent question ends the call instead of recording for fifteen
minutes.** Consent was only ever settled by an answer. In a mock call where the candidate
never spoke after the disclosure, the call ran the full 900 seconds, recorded, with consent
never given, and ended only on the time limit. The interview's `tick` now ends the call once
the consent question has had `CONSENT_ANSWER_TIMEOUT_S` (15 s) of silence. That is counted
from the last thing either side said, so it starts after the disclosure finishes playing and
a hesitation restarts it. Consent is recorded as not given, and the candidate hears a new
fixed line, `CONSENT_UNANSWERED`. Unlike the decline line, it does not tell them "that is
completely fine" about a refusal they never made. It then routes them to a person. On the
old code the two tests that need this failed, and the guard (a hesitation restarts the
wait) passed. Two tests from the previous two entries ticked an unconsented interview late
and expected nothing to happen, which is the bug. They now use a consented interview, or
tick inside the wait. The 15 s figure is a judgement call and wants a look with real
candidates.

**A silent candidate is told the interview is closing.** The spoken wrap-up at 13:30 was
only issued when a caller turn arrived. A candidate who had gone quiet reached the 15-minute
limit without hearing it, and the call simply stopped. The interview's `tick` now delivers
the wrap-up on its own once it is due, consent was given, and both sides have been quiet for
`QUIET_BEFORE_WRAP_UP_S` (2 s). It notes when the agent's audio or any caller transcript was
last seen, so the line never lands across the agent's sentence or the candidate's pause. It
is said once, and it records the wrap-up time that bounds the scored window. On the old code
the two tests that need it failed, and the guard (no wrap-up before consent or before time)
passed.

**The time limit ends a call even when nobody is talking.** The interview only checked the
clock when a backend event arrived. A candidate who went quiet while the agent was not
speaking produced no events, so nothing ended the call. A mock call with the candidate
silent after one answer ran to 1029 seconds against a 900 second limit, and never wrapped up.
The interview now has `tick(t_s)`, which a driver calls on every frame and which ends the
call at the limit. The runner calls it each frame, and its speaking and silence loops stop
pushing audio once the call has ended (a closing line still gets its farewell drain). On the
old code both new tests failed. The spoken wrap-up at 13:30 still waits for a caller turn,
so a silent candidate reaches the end without hearing it. That is the next thing. The
gateway's driver will need to call `tick` too when the tracks merge.

Two full-suite runs this round looked hung. pytest's own timer said 18.65 s while the command
took 943 s, and the power log shows the Mac in maintenance sleep across exactly those
windows. The suite itself was fine.

**A rollover waits for the candidate to finish their turn.** The runner replaced the session
the moment the interview asked for a rollover. What prompts one is a final transcript, and
on the real server a turn's final transcript is released as soon as the candidate starts
their next turn. So a candidate who carried on talking could have the session closed under
them: what it had heard of their new sentence was thrown away, and the new session heard the
rest starting mid-word. The backend contract now has a read-only `caller_speaking`
property, true while the caller's turn is open. It defaults to False, so a driver or backend
that does not know about it behaves exactly as before. The real client reports its open
turn, and the mock its open utterance. The runner holds the seed and rolls on the first
frame after the turn ends. It counts a rollover only when one actually happens. A test
backend records, for every session closed, whether the caller was mid-turn. On the old
runner one of those closes was mid-turn. On the new one none are. The gateway's driver is
not touched. It will want the same check when the tracks merge.

**The client does not end a turn on "um".** The client commits a turn after 640 ms of
silence, and the runtime answers every committed turn. A candidate who said "um" and
paused to think had the turn ended under them, and the model started talking mid-thought.
The interview layer already ignored the hesitation, but the model's reply had already
started. The client now tracks the runtime's id for the open turn, from the turn
acknowledgement, and the text heard in that turn. While that text is only a hesitation, the
turn waits `hesitation_hold_ms` (2000 ms) of silence instead. If they carry on, the text
has words in it and the usual endpoint applies. If they say nothing more, the turn still
commits when the hold runs out. A turn with no text yet is not held, because recognition
lags and holding on that would slow every turn. Text for the previous turn, which keeps
settling after the next one opens, does not count. Barge-in is unchanged. The 2000 ms figure
is a guess, like the endpoint itself, and wants tuning on the box. The mock backend has its
own fixed endpoint and does not do this. On the old client, with the new setting removed
from the tests, the three tests that need the hold failed and the three guard tests passed.

**Genuine quotes are no longer voided over punctuation.** The made-up-quote guard compared
text with only case and spacing ignored. A judge quoting speech adds and drops punctuation
and writes straight apostrophes, so real quotes were rejected and their scores voided: one
with a full stop where the transcript had none, one with a comma where the transcript had a
stop, one in typographic quote marks, and "I didn't trust the retry path" against a
transcript where recognition wrote a curly apostrophe. Quotes are now compared after
folding typography and removing punctuation, keeping apostrophes inside words. The match
is also now of whole words only, so "rote the advisory-lock" no longer passes by sitting
inside "wrote". Missing or different words are still rejected. On the old code five of the
new cases failed. The others (a missing word, words never said) were already rejected and
still are.

**The model judge can no longer cite the interviewer as evidence about the candidate.** The
guard against made-up quotes accepted a quote found anywhere in a question or an answer. A
judge that cited "you personally do", from the question "What did you personally do?",
scored ownership 4 of 4 for a candidate who had said "I was mostly watching", with the
interviewer's words as the evidence. Quotes, and the timestamps looked up for them, now
count only if they appear in the candidate's answers. An existing test had pinned the old
behaviour on purpose (`test_a_quote_from_the_interviewer_counts_as_present`). It is
reversed, because evidence is meant to be what the candidate said. On the old code both new
tests failed. The same check found the guard also rejecting genuine quotes over a trailing
period or a straight versus curly apostrophe. That direction voids a score rather than
inventing one, and is next.

**The report quotes the evidence, not the lead-in.** Each dimension in the report shows one
quote, cut to 72 characters from the end. People lead in before they get to the point, so
in a report built from realistic answers every quote stopped short of its evidence: the
ownership quote ended before "I wrote the advisory lock fix myself", and the tradeoffs quote
at "we gave up some". A recruiter saw a score and a lead-in. The quote is now a window on
the earliest marker the judge matched for that dimension, snapped to whole words, and a
quote with no marker is shortened from the middle. On the old code the ownership quote lost
its evidence. The other three new tests also failed there, but only because the excerpt
function did not exist yet. For technical depth the window lands on the first figure the
judge matched ("six weeks"), which is not always the figure a person would pick.

**The briefing stops asking for evidence the candidate already gave.** Nothing recorded
evidence during a call, so every briefing, for the whole fifteen minutes, said all five
dimensions were still uncovered. A model told "Still no evidence for: ownership" straight
after "I wrote the advisory lock fix myself" asks for ownership again. Each caller answer,
including probe answers, now marks the dimensions it shows, using the same surface markers
the heuristic judge scores on. Those markers are now one shared function, so the live call
and the report cannot disagree about what an answer showed. Vague answers cover nothing.
Scoring still reads the transcript, not this. One engine test had expected
`technical_depth` to stay uncovered after an answer with a figure in it, which was the bug.
It now checks `tradeoffs` instead. On the old engine the three new tests failed.

**The briefing keeps what the probes drew out.** The engine treated an answer to a probe
as deepening the claim, then threw the answer away. After a claim and three probe answers
("I wrote the advisory lock fix myself", "eleven double settlements in six weeks", "two
workers picked up the same batch id"), the briefing listed only the original claim. That
briefing is what a rolled session starts from, and rollover waits for a ladder to finish,
so at every rollover the fresh session knew the project and none of the answers, and could
ask for them again. Each substantive probe answer is now stored with its claim and briefed
under it with its rung ("their own part", "the figure", ...). Vague answers are not. The
live claim and its answers get up to six lines, and older claims fill whatever is left,
so a briefing stays about ten lines. Claims and answers are shortened from the middle,
because they usually end on their figure. On the old engine the three new tests failed.

**A rolled session is told what was asked, and keeps the figure an answer ends on.** When
the call rolls to a fresh session, the seed carries the last exchange so the model can
pick up the thread. It was the last two transcript turns, whoever spoke them. A candidate
who paused mid-answer, or said "um" before answering, filled both lines, so the new session
got half an answer and never the question. Long answers were cut from the end, which kept
the lead-in and dropped the number ("which took p99 from 400 milliseconds down to 30"). The
seed is now the last agent line plus everything the candidate said after it, joined, with
hesitations left out, and long text is shortened from the middle. On the old code the three
new tests failed.

**Plain agreement counts as consent.** The consent check only took a yes that used one of
a short list of words. Run over 17 clear yeses, it refused 12 of them, among them
"Alright", "Sounds good", "I agree", "I consent", "Works for me" and a bare "Fine". Each of
those ended the interview for someone who had agreed. The list now includes them, and the
refusal rules now include the negation of each ("I don't agree", "That doesn't sound good",
"I can't agree to that", "I disagree"), which are checked first. Twelve new yeses and
fourteen negated forms were added to the consent fixtures. On the old check the new tests
failed 15 times, every one a refused yes. All the negated forms were already refused and
still are. "Mm-hmm", "uh-huh" and "right" are still not taken as consent, and a test now
keeps it that way. The earlier slow run (30 s) was noise: the suite runs in about 18 s.

**Scoring pairs a question with its real answer, not with a hesitation.** Scoring matches
each agent line with the reply that follows it. A candidate who said "um" before answering
had "um" recorded as the answer to the question, and their real answer paired with
whatever the agent said in between, such as "Take your time." The heuristic judge reads
only answers, so scores did not change, but the pairing was wrong and a model judge would
have seen it.

A reply that is only a hesitation is now skipped when pairing. An agent line that follows
a hesitation and is not itself a question does not replace the question still waiting for
an answer. A question the candidate only ever answered with "um" has no answer. If the
agent asked a real follow-up question after the hesitation, the next reply is paired with
that question, because that is what the candidate was then answering. That distinction
rests on the question mark, so a rephrased question without one would not replace the
original. The hesitation check moved into its own module, so the interview and scoring
share one definition.

**A candidate thinking mid-answer no longer moves the interview on.** The client closes a
turn after 640 ms of silence, so "um" and a pause in the middle of an answer reach the
interview as a complete answer. In a diagnostic, the probe ladder counted that "um" as
the answer to its outstanding question and asked the next one. Every later answer was then
credited to the wrong question and the ladder ran out one question early: the candidate's
answer about what they personally did was taken as the answer to "give a number", and so
on down. A lone "um" also triggered a session rollover under an eager policy, and it reset
the count of vague answers, restarting a ladder the engine had given up on.

A hesitation mid-interview now leaves the outstanding question outstanding, issues no new
probe, triggers no rollover and leaves the count of vague answers alone. The wall clock
still applies, so a hesitation after the wrap-up time still wraps the interview up.

Scoring still pairs the question with "um" and the real answer with whatever the model
said in between. The heuristic judge reads only answers, so scores are unchanged, but the
pairing is wrong and a model judge would see it. That is the next step.

**A candidate who hesitates before answering the consent question is no longer turned
away.** The client ends a candidate's turn after 640 ms of silence, so "um" followed by a
pause arrives as a complete answer. The consent check reads anything short of a clear yes
as a refusal, so the interview spoke the decline line and ended the call before the
candidate had answered. In a diagnostic, "um", "uh...", "hmm", "well", "so um" and "Um."
all did this, and "um" reached the interview the same way through the real client and
server.

Waiting grants no more consent than declining does. A reply that is only a hesitation, or
empty, now leaves consent unresolved, and the interview waits for the real answer. Only
two hesitations are waited through, so a candidate who never answers cannot hold a silent
call open until the time limit. "mm-hmm" and "uh-huh" are not treated as hesitation,
because they often mean yes. They are still judged as before and read as not consent,
which is a separate question.

**Only the interview itself is scored.** The scoring pass pairs every agent line with the
reply that follows it, and nothing marked where the interview began or ended. So the
recording disclosure and the wrap-up were paired like interview questions. In a
diagnostic, a transcript of three vague answers scored nothing on its own. With a consent
answer and a closing question added, it scored 9 out of 10: technical depth and
communication quoted "Yes, that's fine, because I'd like the recruiter to hear it", and
ownership quoted a question the candidate asked after the wrap-up. A recruiter would have
read a 9 backed by quotes that answered no interview question.

The interview now records when consent was settled and when it wrapped up, the run result
exposes that as the interview's window, and the report scores only the exchanges asked
inside it. A declined call has an empty window, so there is nothing to score. Scoring with
no window behaves as before, which is what the evaluation suites use, since their
transcripts contain only interview exchanges.

**A refusal phrased as an instruction is no longer recorded as consent.** "Sure, skip
the recording" agrees to the call and refuses the recording with no contrast word, so the
previous consent fix did not see it. In a diagnostic, 9 of 10 refusals phrased this way
read as consent, including "Yeah, stop recording please." and "Okay, don't bother
recording."

Two fixes were measured side by side before choosing. The first treated any mention of
recording as a qualification unless it explicitly affirmed recording. It closed all ten,
but turned 2 of 9 genuine yeses into refusals, "Sure, it's fine if you record." and "Yeah,
record whatever you need." The second is a list of words against the recording, applied
only when recording is mentioned: skip, stop, pause, off, without, minus, disable, delete,
erase and bother. It also closed all ten and turned none of the nine yeses into refusals,
so that is what went in.

It only catches opposition phrased with those words. "Sure, as long as nothing is saved."
never mentions recording and is still read as consent; it is recorded as a strict expected
failure. "Sure, delete the recording afterwards." is now read as a refusal, which is
arguable, and is the safe direction.

**A negated or conditional refusal is no longer recorded as consent.** The consent
check counts an answer as consent when it contains an agreement word and no refusal
pattern. A negated agreement matched the first and none of the second. In a diagnostic,
7 of 11 negated agreements read as consent, including "Absolutely not.", "Of course not."
and "I'm not okay with that." Agreement with a condition on the recording did the same
for 4 of 7, including "Of course, but can we skip the recording?" and "Sure thing, but I
object to being recorded." Six plain yeses were all still read correctly, and replaying
the existing consent suite with contractions and expansions changed nothing.

A negated agreement is now a refusal. An answer that attaches a condition to the
recording, meaning a contrast word such as "but" or "unless" together with any mention of
recording, is not a clear yes. The contrast rule only applies when recording is mentioned,
so "yes, but please be quick" is still consent, because a false no costs the candidate
their interview. A refusal phrased as an instruction with no contrast word, "Sure, skip
the recording.", is still read as consent. It is recorded as a strict expected failure
and is the next step.

**A contracted prohibited question no longer gets through.** The prohibited-question
rules are written mostly in full forms, "where are you" and "do you have", and a model
phrasing a question conversationally uses contractions. Replaying every question in the
red-team suite with each applicable contraction applied one at a time, 5 of 12 contracted
variants got through: "Where're you originally from?", "What're you being paid right
now?", "D'you have any children at home?", "Do you've any children at home?" and "D'you
attend church regularly?". No contracted ordinary question was wrongly blocked.

The filter now expands the contractions that have one meaning before it matches, after
typography is folded: "'re" to "are", "'ve" to "have", "d'you" to "do you", and "'s" to
"is" after question words and pronouns only, so a possessive is never rewritten. "'d" and
"n't" are left alone. The first can mean would or had and no rule needs it, and expanding
the second would put "not" inside a question's word order. The replay is now a test, and
every contracted variant must reach the same decision as its full form. The consent check
relies on contracted forms of its own and was not changed.

**How a character is typed no longer changes a compliance decision.** The consent
check and the prohibited-question gate are regular expressions written with keyboard
apostrophes and ordinary spaces, and neither normalised its input. Speech recognisers and
language models often write a typographic apostrophe instead. With one, "Yes, but I'd
rather you didn't record this" read as consent, because the typographic "didn't" slipped
past every refusal pattern while "yes" still matched, and "What's your nationality?" and
"What's your native language?" were allowed to be spoken. With non-breaking spaces every
multi-word rule tested failed to match, "How old are you?" included.

Both gates now fold typographic apostrophes, quotes and every kind of whitespace to plain
characters before matching. Every probe in both red-team suites is replayed in
typographic form and must reach exactly the decision its plain form is labelled with.

On the old gates that replay failed 29 times. 19 of the 23 prohibited questions were let
through, and 8 consent answers changed decision. Six of those were plain yeses read as
refusals. Two were false consent: "yes I understand, but I'd rather not be recorded", and
"well, okay, I guess", where a non-breaking space inside "I guess" hid the hedge. No
ordinary question was wrongly blocked. The first commit message for this fix gave larger
counts than these, because it counted every line of test output that named a test and each
failure is named on more than one line. These are the verified figures.

The same probing turned up a separate gap that typography did not cause: "Where're you
originally from?" is not caught even when typed plainly. That is the next step.

**A candidate's last words are no longer cut off at the end of their turn.** On a
commit the server sent the final transcript at once and closed the turn, before the model
had processed the commit. The model interface says a commit makes the recogniser settle
before its answer is safe, which is when a streaming recogniser confirms its last words,
and anything it confirmed then arrived with no turn open and was dropped by design.
Through the real client and server with a stand-in recogniser, a candidate who answered
"yes" produced an empty final transcript that the client discarded, so consent could
never have been taken, and a four-word answer lost its last word. Only the box can show
how the real recogniser settles, but the server finalised before it could.

The server now holds a committed turn open while the model settles, keeps crediting
recognised words to it, and sends the final transcript when the model opens its reply,
ahead of the reply itself, so the interview hears the answer first. A settle limit, a new
turn or the session closing also finalise it, so a model that never replies cannot strand
a transcript. The limit is a guess until the box.

**Only what the agent actually said reaches the transcript.** The backend contract
defines a final agent text as a record of what was actually spoken, and both backends
broke that. The real client turned any reply text into a final line when the reply ended,
ignoring the server's status, so a reply the candidate talked over, or one the client
stopped to speak a fixed line, was recorded in full. The mock emitted a reply's final text
the moment the reply began, before any audio played, and kept it when interrupted or
replaced. Through the real stack this appeared as a phantom line after a repeated
disclosure, and because that phantom sat between the disclosure and its own echo, the
disclosure was recorded a third time. Scoring pairs each answer with the agent line before
it, so a phantom question also mispaired the candidate's answer.

The real client now emits a final agent line only for a reply the server reports as
completed, and two contract rules pass against it: a reply replaced by a fixed line, and
one the candidate talks over, are never recorded as spoken. Only the real client runs on
the box, so the defect is fixed where it matters.

The mock and the speaking backend still record a reply the moment it starts. The change
that makes them wait for the last frame was written and is saved outside the repo, but it
breaks a gateway test that feeds fifteen frames and expects the greeting already in the
transcript. That test belongs to the call-joining track, so the mock change waits on that
team. Until then the two rules are strict expected failures for those backends, which will
fail loudly the day they conform. The speaking backend plays every line in full by design,
so nobody can cut in, and it is exempt from the second rule entirely.

**A candidate who talks over the disclosure is told again before consent is taken.**
The interview ignored an interruption, so whatever the candidate said over the opening
disclosure counted as their answer to whether the call could be recorded. Through the
real client and server, a candidate who said "yeah go ahead" over the disclosure cut it
off, the server cancelled it part way through, it was never repeated, consent was
recorded, and the transcript still showed the disclosure in full. That put a candidate
on record as agreeing to a recording they may never have heard announced, which is the
first of the non-negotiables in docs/06-compliance.md.

Before consent is settled the only thing the agent has said is the disclosure, so an
interruption in that window now means it was not heard. The interview does not treat the
next utterance as an answer; it repeats the disclosure in full and takes consent from the
reply after that, and it flags the repeat so a reviewer can see it happened. An
interruption once consent is settled behaves as before.

Running that through the real client and server sent the disclosure four times and never
took consent. The candidate had interrupted only once. The model starts replying on its
own the moment a candidate's turn ends, and the real client stops that reply to make room
for a fixed line; it reported doing so as an interruption, exactly as if the candidate had
talked over the agent. So every repeat of the disclosure flagged itself as interrupted and
triggered another. The mock replaces its reply without reporting anything, which is why
only the real stack showed it. Stopping the agent's own reply for a fixed line is no
longer reported as an interruption, and a contract rule holds every backend to that.

The same trace shows the reply that was stopped still landing in the transcript as if the
agent had said it. That is the next step.

**The agent stops interrogating once it has said it is out of time.** At 13:30 the
interview speaks its wrap-up line and leaves the last ninety seconds for the candidate's
questions and next steps. Only the answer that triggered the wrap-up stopped short of
probing. Every later answer fell through to the normal path, so in a diagnostic run the
agent said it was out of time and then walked a whole new ladder over the next four
answers, ending by steering the model to ask what broke afterwards in reply to the
candidate asking whether they had any questions. The same path could also roll the
session and pay for a pause in the closing minute. Once the wrap-up time has passed,
every answer now stops before probing and rollover; the briefing still goes out, since it
tells the model to close.

**A candidate who goes vague part way down a ladder no longer switches rollover off.**
Two general answers in a row make the engine abandon a probe ladder and tell the model
to change topic. The rollover guard still counted that ladder as in progress, because it
only looked at how far down the claim had got, and vague answers never start a new claim
to replace it. Rollover checks that guard first, so a candidate who went vague mid-ladder
switched rollover off for the rest of the call. In a diagnostic 300-second call with an
eager policy, a candidate who stayed vague after stalling got no rollover at all, while
one who became specific again rolled four times. On a real fifteen-minute call the model
would have run many times past its two-minute memory with no error anywhere.

The guard now uses the same stall rule that stops the questions, held in one place so
the two cannot drift apart again. The guard is still checked before frame pressure;
a single session's frame cap is longer than the longest call, so that order cannot end
a call, and it was left alone.

**Rollover no longer throws away the last question of the probe ladder.** A long
interview through the real client and server now rolls its session over the wire
cleanly: every replaced connection closes, every new one starts from its seed, and no
server error is raised. It also showed that every replaced session had ended on the same
instruction, to ask what broke afterwards, which the next session never received.

The rollover policy waits for the probe ladder to finish so it never drops a thread
mid-descent. It counted the ladder finished the moment the last question was issued
rather than when the candidate answered it, so it rolled on exactly that turn, and the
question went into a model that closed a moment later. Because the policy seeks out a
finished ladder, this was the normal case, not a rare one, and the rung it lost is the
one most likely to separate real experience from a rehearsed story. The final rung now
counts as in progress until it is answered, so the same session asks it and hears the
reply, and the rollover comes a turn later with nothing pending.

**A candidate who declines now hears the decline.** Holding a mid-turn line on the
client was only half of it. The runner closed the session the moment the call ended, so
a line the client was holding, or one the server had just accepted, never got the audio
frames it needed to play. When a call ends on a spoken line the runner now keeps the
session open until that line has played. It first waits for the line to start, because a
line the client is holding only goes out once the candidate's turn closes, and the old
wait gave up after 300 ms of silence, two frames short of that happening. It also keeps
counting the agent's audio after the call has ended, which it had stopped doing after the
first event of each batch. An end with nothing to say, like the time
limit, still closes at once, and so does a backend failure. The decline is now voiced
through the real client and server after both a short pause and an ordinary one.

**A fixed line asked for mid-turn is held until the turn ends.** The server refuses a
fixed line while the candidate's turn is still open. On a declined consent with a short
pause, the decline line hit exactly that: the client sent it, the server refused it as
mid-turn, and the refusal was still unread when the call closed, while the transcript
recorded the line as spoken. The same refusal is reachable on the box whenever a
candidate keeps talking straight after an answer. The client now holds such a line and
sends it the moment the turn commits, in order.

On its own this does not yet get the decline heard. The runner still closes the session
the instant the call ends, before a held line can play. That is the next step.

**A backend failure no longer crashes the interview.** The whole interview now runs
through the real client and the real server over the loopback, and on the normal path
the layers agree: consent is taken over the wire, the disclosure comes back as audio
from the server, steers reach the model, every turn is delivered and no server error is
raised. The stand-in model has no language model, so every reply is its one fixed line;
what that proves is agreement between layers, not a good interview.

Pointing it at a failure found a crash. When the runtime closed a session at its frame
cap, the client queued a fatal error that the interview runner never read, and the next
frame went into the closed session and raised. On the box, any runtime failure part way
through an interview would have ended with no transcript and no report. The runner now
records backend errors, and on a fatal one ends the call with the reason and stops
pushing audio, while keeping everything said before the failure.

**The real client and the real server have now talked to each other.** Both halves of
the wire were built against the same protocol and tested only against their own fakes:
the client against a fake connection that said whatever a test told it to, the server
against messages built by hand. Nothing had ever passed one half's real output to the
other. An in-memory loopback now does, serialising every message in both directions,
stepping the model stand-in with the real frame loop and routing through the real
dispatcher.

It found no protocol mismatch. The handshake, audio framing, a whole turn with an
audible reply, steer, say, barge-in and close all agree across the wire, and the server
raises no error in any of them. One of my own assertions was wrong: it expected no agent
audio at all after a barge-in, and failed because the agent correctly answered the
interruption once the candidate stopped. Checking the message sequence showed the old
reply cancelled and a new one started, and the test now asserts that instead.

**A replaced session stops being read.** Making the real backend discard its queue on
close only covered one backend. The mock and the speaking backend take a snapshot of
their queue when reading starts, so when a rollover replaced a session partway through,
the runner went on delivering the old session's remaining events to the interview. Those
are words from a model that had just been closed, and they would have been recorded and
scored. The runner now stops reading as soon as the session it was reading from is
replaced or the call ends, which holds for every backend regardless of how its queue
behaves.

**One contract, run against every backend.** The backends were kept in step by tests
copied from one file to another, and the copies drifted. That is how `say` and `steer`
came to crash on every call on the real backend while passing on the mock. The fake
connection lived inside the real backend's own test file, so no other suite could run
that backend at all. It now lives in a shared test module, and a single contract suite
runs the mock, the real backend and the speaking backend through the same rules. A guard
fails if the contract gains a method no rule exercises.

Building it surfaced one more divergence. Closing a mock session discards whatever it had
queued; closing a real session kept it, and polling afterwards still returned it. During
a rollover the runner closes the old session while still reading it, so on the box the
old model's leftovers would have flowed into the transcript as words nobody heard. A
caller's close now discards. A session that ends itself still keeps its final error,
because that is how the caller learns why the call died, and four existing tests depend
on exactly that.

**Rollover no longer crashes the first long call on the box.** The runner replaced a
session by opening the new one before closing the old, so there would never be a moment
with no session. The real backend refuses a second live session and the server closes a
second connection as busy, so on the box the first rollover of every long call would have
raised. Every rollover test ran against the mock, which allows two sessions at once.

The swap now closes first and then opens, and the candidate hears the beat of silence the
design already accepted. The new session is also steered with the whole seed rather than
the briefing alone. The last exchange was being dropped, and it is the part that lets the
agent continue mid-thought instead of starting the topic over. Rollover is now tested
against a backend that enforces one live session and against the real backend class.

Testing that against the real backend class found two more crashes in code written two
iterations earlier. On the real session, `say` and `steer` referred to a module name the
file never imports, so every call raised. `say` also called a property as if it were a
method, which raised again even once the first was fixed. The server-side fix that
delivers briefings to the model would have been unreachable, because the client could not
send one. Both methods had only ever been tested on the mock and on the server session.
They are now tested directly on the real session, including a fixed line spoken over an
agent that is mid-response.

**Briefings and the disclosure now reach the model.** The server accepted `say` and
`steer`, stored each one as state, and nothing ever came to collect it. Every briefing,
every rollover seed and the consent disclosure would have arrived at the box and gone no
further, which is the memory layer switched off without an error. Both halves passed
their own tests, the same shape as the three integration bugs before it.

They are now actions like every other message that needs the model, routed through the
dispatcher and the frame loop in order. A steer never overtakes the audio it describes, a
say never overtakes the end of the candidate's turn, and a barge-in still jumps ahead of
both. The model interface gained the two methods they end at, and the real model marks
them as seams 4 and 5 for the box. A new test reads the session's source and fails if it
ever emits an action the dispatcher does not route.

**A cough no longer interrupts the agent.** The voice gate decided both barge-in and
turn opening from the loudness of a single 20 ms frame, so a door, a keyboard or someone
clearing their throat stopped the agent mid-sentence. The runtime design had already
named this the thing most likely to embarrass a demo; nobody had pointed anything at it.

Five synthetic probes now do. Sustained speech yields the floor, a quiet voice is still
heard, room tone never opens a turn, and neither a one-frame cough nor a two-frame knock
interrupts. The gate waits for loudness to persist across 60 ms while still dating the
onset from its first frame, so the pre-roll keeps the start of the word. `make gate`
runs it.

**An imperfect transcript now scores the same as a clean one.** Everything the scorer
had been fed was hand-written and correctly punctuated, and nothing on the box will look
like that. Five realistic recognition degradations of the same strong answer:
lowercased and unpunctuated, sentence boundaries lost, short words dropped, a
self-correction left in, a stuttered opening.

Four held. The self-correction did not. "I I— wrote the reproduction harness" stopped
reading as first person, because the repair falls exactly between the pronoun and its
verb, which is where the ownership signal lives. A candidate claiming their own work
scored as having claimed nothing.

That is the failure docs/05 names as the most probable route to a discriminatory
outcome: recognition is worse on some speakers, the scorer sees a degraded transcript,
and the transcription gap becomes a scoring gap. Stutters and repairs now collapse
before anything judges content, while quoted evidence keeps the candidate's own words.
`make asr` runs it.

**The scorer could not read a number.** The interview's central probe is "give me a
number", and the thing that scores the answer only recognised digits. "Ninety percent",
"twelve hundred a second" and "eleven double settlements over six weeks" were all
invisible. People say numbers out loud and recognition writes them as words, so the
single most important piece of evidence the interview is designed to extract was the one
piece the scorer could not see.

The engine had the same blind spot in the other direction: an answer full of spoken
figures read as vague, which stalled the probe ladder on a candidate who was being
precise.

Number words are now recognised in both. "One" is deliberately excluded, because "one of
the things we did" is not a measurement and a false positive credits an answer that gave
no figure at all.

**The demo takes consent again.** The speaking backend added for the demo cannot
recognise speech, so it never reported when a candidate stopped talking, and the engine
saw only its own voice: consent unresolved, no probe issued, no rollover possible, while
the transcript still looked plausible. That was the demo a judge would have watched.

The harness now supplies the turn boundary when a backend cannot, since the simulated
caller knows what it said and when it stopped, and it counts how often it had to. A
non-zero count is the honest signal that the audio is real and the listening is not.
Both backends now reach the same consent, the same probes and the same score.

Chasing that surfaced a genuine bug in the scoring pass. A candidate who pauses and then
keeps talking produces two turns in a row, and the second was being silently discarded.
That is often the specific half, because they have had a moment to remember the number.
In one transcript it was the difference between a 7 and no score at all.

 The speaking backend added for the demo never
reports that the candidate said anything, so with it in place consent is never resolved,
no probe is issued and no rollover can fire. That is a fine thing for a canned demo to
be and a dangerous thing to mistake for a screening call. If a judge asks whether the
demo took consent, the honest answer is that the disclosure was spoken and the answer
was never processed. Tests now state the difference between the two backends explicitly.

**The consent gate, red-teamed.** `make consent` fires 32 answers at the gate that
decides whether a call happens at all. Its two failure directions are not equally bad: a
false yes records someone who declined, a false no ends the interview for someone who
agreed. The first is the thing this project promised not to do.

Two answers were being read as consent that were not. "I'm not sure, yes maybe" and
"well, okay, I guess" both contain an agreement word while meaning something else, and
both would have started recording. Three agreements were being read as refusals, because
English says yes with refusal words constantly: "no problem", "no worries" and "I don't
mind" were all ending calls on people who had just agreed.

The gate now checks hedging first, rewrites agreement idioms, and only then looks for a
literal refusal. Silence is still not agreement.

Removing the fix also surfaced a shadowing duplicate of the decision function, where the
older definition was the one actually running. Every intermediate value said yes while
the function returned no.

**The prohibited-question gate, red-teamed.** `make redteam` fires realistic phrasings
at the block list: not caricatures, but the way a model actually produces these while
building rapport. It caught 19 of 23 on the first run and wrongly blocked one ordinary
sentence.

The four that got through were all near-misses of an existing rule. "First language"
where only "native language" was covered. "Medical conditions" where the pattern matched
the singular and a word boundary. Salary history asked in the progressive and the
passive, where only the textbook form was covered. Each is a question a candidate could
genuinely have been asked.

The false positive was "citizen" as an ordinary noun in a data model, which the gate read
as a question about immigration status. A gate that blocks normal engineering talk is a
gate someone turns off.

All five are fixed and each is now a regression test.

**Matched-pair bias evals, and the bug they found.** `make bias` scores the same
substantive answers twice, varying only delivery: verbal filler, non-native phrasing,
hedging, terseness. Any score difference is a defect.

It immediately found one in our own code. Verbal filler alone moved a candidate from
7/10 and "advance with reservations" to 4/10 and "do not advance", on identical facts,
identical numbers and identical ownership. The vagueness detector treated "um" and "you
know" as a lack of substance. Filler is delivery, and it correlates with nervousness and
with speaking a second language, so that was the system scoring how someone sounds.
Filler is now stripped before any judgement and the quote keeps their own words.

This is the failure mode docs/05 names as most likely, and it was live in the
codebase until a matched pair went looking for it.

**An instrument for telling whether a change helped.** `make evals` scores six
hand-labelled calls and reports band agreement, score spread, and which dimensions a
human expected evidence for that the judge found nothing on. Without it, every prompt
edit and model swap is a guess.

The labels carry a rationale so they can be argued with, and the suite deliberately
includes the two cases a judge gets wrong in opposite directions: a candidate who is
articulate and says nothing checkable, and one whose call was short but specific. A
judge that conflates short with thin rejects people for a dropped connection.

It also watches for score compression. Every scored call landing on one number means the
rubric is decorative: the reports look confident and carry no information. That failure
is invisible in any single report and obvious across a suite.

The heuristic judge currently agrees with the human label on four of six, which is the
honest baseline a real judge has to beat.

**A judge with a model behind it.** `ModelJudge` scores one dimension per call against
any callable that takes a prompt and returns text, so it works with whatever is on the
box without the scoring code knowing anything about it.

Its important behaviour is distrust. A model asked for evidence will sometimes cite a
quote that is not in the transcript, and a fabricated quote in a hiring report is worse
than no report. Every citation is checked verbatim against the transcript, and one that
cannot be found voids the whole verdict rather than being quietly dropped while the
score survives. A model that fabricates everything produces "insufficient signal", which
is the correct outcome and also a usable alarm. Unreadable output becomes insufficient
evidence, never a guess.

**Turn taking fixed.** The demo was reporting six interruptions in a twenty-nine second
call. The driven runner waited for the agent by watching the transcript, which grows the
moment an utterance starts rather than when it ends, so it returned while seconds of
speech were still queued and the simulated caller talked over every single turn. It now
waits on the audio. Interruptions went to zero for a caller who waits, and the one
deliberate barge-in in the script is honoured rather than ignored.

**The demo runs the real path.** `make demo` now puts the interview engine in charge of
a backend session rather than letting the backend's own script drive, which is the
arrangement the real system uses. Wiring it found three integration bugs that every unit
test had missed: the disclosure appeared twice because the backend echoes back what it
spoke and both copies were recorded; the candidate's words never reached the transcript
because the endpoint fires during the silence *after* speech, not during it; and after a
session rollover the loops kept pushing audio into the session that had just closed.
Rollover would not have worked at all on the box.

**The backend contract learned to be steered.** Wiring the driver to a real session
exposed the gap: the contract could carry audio but gave the interview layer no way to
make the model say a fixed sentence or to hand it context. `say` speaks exact wording
for the utterances that are ours and not the model's, the disclosure, the consent
request, the wrap-up. `steer` puts a briefing into the model's working context without
speaking it. They are separate calls, and separate wire messages, because they fail
differently: a `say` that leaks into context makes the model repeat itself, and a
`steer` that reaches the speaker reads the agent its own notes aloud. The server refuses
a `say` mid-turn, because speaking over a candidate is the failure they remember.

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
