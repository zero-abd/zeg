"""Fixed text the model is not trusted to remember.

The disclosure and the consent request are legal requirements, not stylistic
choices, so they are literals here rather than instructions in a system prompt.
See docs/06-compliance.md.
"""

GREETING = (
    "Hi, thanks for making the time. Before we start, two things you should know. "
    "I am an AI interviewer, not a person. And this call is recorded so a human "
    "reviewer can go through it afterwards. Is that okay with you?"
)

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

#: Spoken over the agent when it starts asking something it must not ask. Saying it
#: cancels the model's own reply, so the question is cut off rather than finished. The
#: candidate hears a change of subject, not an apology for a question they were half
#: asked, and the flag on the record says what happened.
PROHIBITED_REDIRECT = (
    "Sorry, let me stay on the technical side. Tell me more about the part of that "
    "work you did yourself."
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
