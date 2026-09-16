"""Asking to stop, once the interview is under way.

The two directions are not equally bad. A missed withdrawal keeps recording somebody who
asked us to stop. A false one ends an interview that was going fine. The first is worse.

But this runs on every answer in a technical interview, where "we stopped the retries" is
an ordinary sentence, so the false-positive cases below are as much the point as the
withdrawals.
"""

import pytest

from zeg.withdrawal import reads_as_withdrawal

WITHDRAWALS = [
    "Actually, can you stop the recording?",
    "Sorry, please stop recording me.",
    "I would like to stop.",
    "I want to stop, sorry.",
    "Can we stop here?",
    "Can we stop?",
    "Please stop.",
    "I'd like to stop.",
    "Could you delete the recording?",
    "Please turn off the recording.",
    "I withdraw my consent.",
    "I no longer consent to this.",
    "I don't consent to being recorded.",
    "I'm not comfortable being recorded any more.",
    "Stop the interview, please.",
    "Can we end the call?",
    "Take me off the recording.",
    "I'd rather you didn't record this.",
]

#: Things a software engineer says in an ordinary answer. Every one of these ending the
#: interview would be its own kind of failure.
ORDINARY_ANSWERS = [
    "We stopped the retries after the third attempt.",
    "We had to cancel the call to the payments API when it timed out.",
    "I stopped the nightly job and reran it by hand.",
    "The consumer stops recording metrics after an hour of inactivity.",
    "We record every request to the audit log.",
    "So the deploy was cancelled and we rolled back.",
    "I ended up rewriting the reconciler.",
    "That call is made once per batch.",
    "We turn off the cache during the migration.",
    "It stops when the queue drains.",
    "I want to stop guessing and actually measure it.",
]


@pytest.mark.parametrize("text", WITHDRAWALS, ids=WITHDRAWALS)
def test_a_candidate_asking_to_stop_is_heard(text):
    assert reads_as_withdrawal(text), text


@pytest.mark.parametrize("text", ORDINARY_ANSWERS, ids=ORDINARY_ANSWERS)
def test_an_ordinary_technical_answer_does_not_end_the_interview(text):
    assert not reads_as_withdrawal(text), text


def test_typography_does_not_decide_it():
    assert reads_as_withdrawal("I’d like to stop.")
    assert reads_as_withdrawal("I’d rather you didn’t record this.")
