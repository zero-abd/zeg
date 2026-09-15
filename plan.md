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
