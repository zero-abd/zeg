# Why on the box and not in the cloud

This is the decision the whole product hangs on, so it is worth writing down properly
rather than leaving it as a slogan on the landing page.

The short version: the cloud is the better engineering choice and the worse product.
We are not running locally because it is faster or cheaper to build. We are running
locally because of what it removes from the customer's side of the table.

## The argument that actually closes the deal

An SMB buying a hosted screening tool is not buying software. They are buying a
procurement exercise. A vendor in the audio path is a data-processing agreement, a
sub-processor list they have to maintain, a security questionnaire someone has to fill
in, and a renewal conversation every year with a legal team that did not want the tool
in the first place. For a fifty-person company that has no legal team, that exercise
costs more than the subscription does.

Automated hiring is also among the most regulated uses of AI there is, and the rules
follow the candidate, not the company. See `06-compliance.md` for the list. Every one of
those obligations gets harder to discharge when the audio has been handed to someone
else, because now the answer to "where did this recording go" is a diagram instead of a
room.

We do not make that review smaller. For this pipeline we delete it. Nothing in the
diagram is a vendor, so there is no sub-processor to disclose, no transfer mechanism to
argue about, and no third party whose breach becomes the customer's notification duty.
That is the sentence that sells this, and it is only true while it is literally true.

## Residency is physical, not contractual

Cloud data residency is a promise. It is a region flag, a contract clause, and trust
that the flag and the clause match what the machines are doing. It is usually fine. It
is never inspectable by the customer.

On a box, "where does the candidate's voice live" is a question about which rack it is
in, and the customer can answer it by walking over and pointing. IT can firewall it,
patch it, and audit it like any other appliance they own. Pull its network cable once the
call has connected and the interview still finishes, because the only thing crossing the
network was the candidate's own connection.

## The rubric needs a model that does not move

This one gets overlooked and it may be the most important of the lot.

Our success criterion is agreement with a human screener, and the evals in
`zeg/evals/` exist to measure whether a change to the system helped or hurt. That whole
apparatus assumes the thing being measured holds still. A hosted model does not. It gets
updated on a schedule you do not control, and the update is usually an improvement in
general and an unmeasured change in the one narrow judgement you calibrated against.

The failure is quiet. Nothing errors. The reports keep looking confident. The band a
candidate lands in simply moves, and you find out at the next bias audit, if you find out
at all. In a tool that decides who gets a second conversation, a silent distribution
shift is the worst class of bug we can ship.

Weights on our disk at a version we chose means the rubric we calibrated is the rubric
that runs. When we do change models, we change them deliberately and the eval suite says
what it cost us.

## The cost curve is the wrong shape, not just the wrong number

Hosted screening is priced per interview, so the bill grows with exactly the activity the
customer is trying to increase. A company that hires harder pays more for the privilege,
forever. A box is bought once, and after roughly five hundred interviews the marginal
cost of the next one is electricity.

Our arithmetic is ten dollars an interview against a five-thousand-dollar machine, which
is our own estimate and not a quote from anyone. Put different numbers in and the
crossover moves; the shape does not, and the shape is the argument.

## Latency, which is the weakest of the good arguments

Taking the network round trip out of a conversational loop is real and it helps. It is
also the argument I would lead with least, because a well-run hosted voice API is already
fast enough that a candidate would not notice, and our own box has constraints of its own
that eat the saving back. `03-latency-budget.md` predates the model choice and should be
read as a sketch.

Use this as a supporting point. Do not build the pitch on it.

## What we give up, plainly

**Concurrency.** One conversation at a time on this box, because the model's state is
recurrent and a single GPU serves a single call. Hosted scales to a hundred candidates in
an afternoon without anyone thinking about it. Our answer is more boxes, which is also
the business model, but it is an honest limitation and we should say it out loud when a
judge or a customer asks rather than being caught by it.

**Model ceiling.** We run what fits in the box, quantised. A frontier hosted model would
be a better interviewer. We are betting that a small model driven by a strict state
machine, with the scoring done afterwards where latency does not matter, closes enough of
that gap. That bet is measurable and the evals are how we measure it.

**Someone has to own the machine.** Patching, weights, the driver and kernel it is
qualified against, the day it falls over mid-call. The customer inherits an appliance and
the obligations that come with one.

**No elasticity.** Demand is spiky. Hiring happens in bursts. A box does not care what
your Tuesday looks like, and it is idle most of the month.

None of that is a reason to change course. All of it is a reason not to pretend the
tradeoff is free.

## The rule that follows from all of this

**No cloud fallback.** Not for load, not for a failure mode, not for "just the scoring
pass", not quietly in a config flag someone adds at two in the morning. A single hosted
call in the path puts every obligation above back on the customer's desk and makes the
central claim false. If the box cannot serve the call, the agent apologises, says a human
will follow up, and ends the call cleanly. That is a worse call and an intact promise.

If a customer ever explicitly asks for a hosted component, that is their decision to make
with their counsel, and it is a different product with a different pitch.

## What would change our minds

Written down so it can be argued with later:

1. Human-to-human agreement on the seed set comes back low enough that scoring is not a
   viable framing at all. Then this is structured evidence gathering, the model matters
   less, and the case for owning it weakens.
2. Concurrency turns out to be what customers buy on, not compliance. Measure this with
   real buyers before believing either answer.
3. Confidential-computing hosting matures to where a customer's counsel treats it the way
   they treat a box in their own rack. That is the scenario that makes this whole document
   obsolete, and it is not here yet.
