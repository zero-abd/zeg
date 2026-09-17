"""Telling a question apart from an answer, at the consent gate.

Only the kinds that can be answered honestly are recognised. Anything else falls through
to the gate, which is the conservative direction: an agent that improvises about what
happens to a recording is worse than one that hands the call to a person.
"""

import pytest

from zeg.asks import asks_about_consent

QUESTIONS = [
    ("what happens to the recording?", "recording"),
    ("who gets to see this?", "recording"),
    ("how long do you keep it?", "recording"),
    ("what do you do with it afterwards?", "recording"),
    ("is the recording shared with anyone?", "recording"),
    ("are you a real person?", "ai"),
    ("am I talking to a bot?", "ai"),
    ("are you an AI?", "ai"),
    ("is this a recording?", "ai"),
    ("sorry, could you repeat that?", "repeat"),
    ("what was the question?", "repeat"),
    ("I didn't catch that", "repeat"),
    ("does it have to be recorded?", "necessity"),
    ("do I have to be recorded?", "necessity"),
    ("is that mandatory?", "necessity"),
]

#: Answers, not questions. These must reach the gate untouched.
ANSWERS = [
    "yes that is fine",
    "sure, go ahead",
    "no thanks",
    "I'd rather not",
    "I guess so",
    "um",
    "",
    "absolutely not",
    "fine by me",
]


@pytest.mark.parametrize("text,kind", QUESTIONS, ids=[q for q, _ in QUESTIONS])
def test_a_question_is_recognised_and_classified(text, kind):
    assert asks_about_consent(text) == kind


@pytest.mark.parametrize("text", ANSWERS, ids=[a or "silence" for a in ANSWERS])
def test_an_answer_is_left_to_the_gate(text):
    assert asks_about_consent(text) is None


@pytest.mark.parametrize("text", [
    "Sorry, what does this team actually work on day to day?",
    "How does the team split on-call between people",
    "Can you tell me more about the role first?",
    "so what is the stack like",
])
def test_a_candidates_question_is_recognised(text):
    from zeg.asks import is_question

    assert is_question(text), text


@pytest.mark.parametrize("text", [
    "What I did was rewrite the reconciler after the outage",
    "How we fixed it was an advisory lock",
    "We rewrote the reconciler after the outage",
])
def test_an_answer_that_starts_like_a_question_is_not_one(text):
    from zeg.asks import is_question

    assert not is_question(text), text


def test_typography_does_not_decide_it():
    assert asks_about_consent("I didn’t catch that") == "repeat"
