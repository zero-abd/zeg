"""Fixed text the model is not trusted to remember.

The disclosure and the consent request are legal requirements, not stylistic
choices, so they are literals here rather than instructions in a system prompt.
See docs/06-compliance.md.
"""

#: Words a second of speech carries, for estimating how long one of these lines takes to
#: say. Used only to keep one line from landing on another: a timer that speaks cancels
#: whatever is in flight, and the wrap-up mark has to leave room for the wrap-up and the
#: goodbye before the call ends. So it must never read short, and reading long only costs
#: a wait.
#:
#: Measured by synthesising every line below: 3.33 words a second at the median, 2.90 at
#: the slowest, on a laptop voice rather than the box's. Set under the slowest of those,
#: which leaves every line's estimate above its measured length. Worth re-measuring
#: against the voice the box actually uses; test_prompts.py is that measurement.
WORDS_PER_SECOND = 2.75


def speech_seconds(text: str) -> float:
    """About how long this line takes to say."""
    return len(text.split()) / WORDS_PER_SECOND


GREETING = (
    "Hi, thanks for making the time. Before we start, two things you should know. "
    "I am an AI interviewer, not a person. And this call is recorded so a human "
    "reviewer can go through it afterwards. Is that okay with you?"
)

#: Answers to the questions a candidate asks before agreeing. Each one is followed by the
#: consent request again. They say what is actually known: an agent that improvises about
#: how a recording is stored is worse than one that offers to have a person confirm it.
CONSENT_ANSWERS = {
    "ai": (
        "Yes, I am an AI interviewer, not a person. If you would rather speak to a "
        "person instead, say so and I will arrange that."
    ),
    "recording": (
        "A human reviewer on the hiring team goes through the recording afterwards. I "
        "do not have the details of how it is stored or for how long, and I can have "
        "someone from the team confirm that for you."
    ),
    "necessity": (
        "The recording is how a human reviews the interview afterwards, so I cannot run "
        "it without one. If you would rather not be recorded, we can stop here and I "
        "will ask the team to arrange a call with a person."
    ),
}

#: Asked again after one of those answers, and after a request to repeat.
CONSENT_REASK = "So, is it okay with you if I record this call?"

#: Spoken if consent is refused. The call then ends and routes to a human.
CONSENT_DECLINED = (
    "That is completely fine. I will pass this back to the recruiting team and "
    "someone will reach out to arrange a call with a person instead. Thanks for "
    "your time."
)

#: Spoken if the consent question gets no answer at all. Silence is not agreement, so the
#: call ends the same way a refusal does, without telling the candidate they refused.
CONSENT_UNANSWERED = (
    "I have not heard an answer, so I will not go ahead with a recorded interview. "
    "I will pass this back to the recruiting team and someone will reach out to "
    "arrange a call with a person instead. Thanks for your time."
)

#: Spoken when the candidate asks to stop, once the interview is under way. The call ends
#: there: consent is not a gate that is passed once, and carrying on after being asked to
#: stop is the thing the consent gate exists to prevent.
CONSENT_WITHDRAWN = (
    "Of course. I am stopping the interview here. I will pass this back to the "
    "recruiting team and someone will be in touch. Thanks for your time."
)

#: Spoken when the candidate asks to speak to a person instead. The disclosure offers
#: this in the first sentence of the call, so it is a promise, not a courtesy.
HUMAN_REQUESTED = (
    "Of course. I will stop here and ask the recruiting team to arrange a call with a "
    "person. Thanks for your time."
)

#: Spoken over the agent when it starts asking something it must not ask. Saying it
#: cancels the model's own reply, so the question is cut off rather than finished. The
#: candidate hears a change of subject, not an apology for a question they were half
#: asked, and the flag on the record says what happened.
PROHIBITED_REDIRECT = (
    "Sorry, let me stay on the technical side. Tell me more about the part of that "
    "work you did yourself."
)

#: Spoken when a candidate has said nothing for a few seconds after a question. The model
#: only speaks in reply to a finished caller turn, so without a line of ours a silent
#: candidate got silence back, for as long as the interview had left.
SILENCE_NUDGE = "Take your time. If it helps, I can ask about something else."

#: Fixed lines that are not questions and do not replace the question still waiting for an
#: answer. After a nudge, the candidate's answer was paired with "Take your time" as its
#: question in the report, and a rolled session was told that was the last thing asked.
#: Deliberately a closed list: a line without a question mark is often still a question
#: ("Tell me about the rollout."), so absence of "?" cannot be the rule.
#: The answer to "are you an AI?" is one too: asked mid-answer, a rolled session was seeded
#: with it as the last thing the interviewer said, and never learned the question pending.
INTERJECTIONS = (SILENCE_NUDGE, CONSENT_ANSWERS["ai"])

#: Spoken when the silence goes on. It carries a question of its own, because moving on to
#: nothing leaves the candidate in the same silence.
SILENCE_MOVE_ON = (
    "No problem, let's move on. Can you tell me about a different project you worked on "
    "recently?"
)

#: Spoken just before the time limit ends a call. The call used to simply drop, mid-sentence
#: if the agent was answering the candidate's own closing question.
TIME_UP = "We're out of time. Thank you for talking with me today."

#: Spoken when the candidate has nothing more to ask after the wrap-up. The call ends after
#: it, instead of waiting out the clock on a silent, recorded line.
CLOSING = (
    "Thanks for your time today. The hiring team will review this and be in touch about "
    "next steps. Goodbye."
)

#: Spoken when the wall clock reaches the wrap-up mark, regardless of context.
WRAP_UP = (
    "That is about all the time I have. Is there anything you wanted to ask before "
    "we finish?"
)

SYSTEM_PROMPT = """\
You are conducting a 15-minute technical screening call for a software engineering
role. You are not making a hiring decision; you are gathering evidence a human will
review.

Ask one question at a time. Keep your turns under twenty seconds of speech.

When a candidate makes a claim, probe it: what they personally did, a number, a
tradeoff they accepted, what broke afterwards. Stop descending when the answer
becomes specific, or when two answers in a row stay general.

Never ask about age, family, pregnancy, national origin, citizenship beyond a single
work-authorisation question, religion, disability, health, arrest record, or salary
history.

If asked whether you are an AI, say yes immediately and offer a human alternative.
"""
