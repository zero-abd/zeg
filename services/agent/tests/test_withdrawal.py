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
    "I don't want to continue.",
    "I don't want to do this anymore.",
    "Let's end the interview here.",
    "Can we end this call?",
    "I'm done, I want to stop.",
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
    # Each of these ended the interview.
    "I'd like to stop and think about that for a second.",
    "Please stop me if this is too much detail.",
    "I want to stop there, that's the gist of it.",
    "We end the call when the websocket drops.",
    "Let's stop the recording of logs at debug level.",
    "I'd like to end on that point.",
]


@pytest.mark.parametrize("text", WITHDRAWALS, ids=WITHDRAWALS)
def test_a_candidate_asking_to_stop_is_heard(text):
    assert reads_as_withdrawal(text), text


@pytest.mark.parametrize("text", ORDINARY_ANSWERS, ids=ORDINARY_ANSWERS)
def test_an_ordinary_technical_answer_does_not_end_the_interview(text):
    assert not reads_as_withdrawal(text), text


HUMAN_REQUESTS = [
    "I'd rather speak to a person.",
    "I would prefer to talk to a human.",
    "Can I speak to someone instead?",
    "Could I talk to a real person?",
    "May I speak to a recruiter?",
    "Can you put me through to someone?",
    "Is there a person I can talk to?",
    "Is there someone I can speak to?",
    "I want to talk to someone else, a person.",
    "Can I speak to someone?",
    "Can you transfer me to a recruiter?",
]

#: Ordinary answers that mention talking to people. Ending the interview on any of these
#: would be its own failure.
ABOUT_COLLEAGUES = [
    "We talk to the payments team every week about it.",
    "I spoke to the on-call engineer and we rolled it back.",
    "You can talk to the API directly if you need to.",
    "I had to speak to three teams before anyone owned it.",
    "The service talks to a person-lookup endpoint.",
    # Each of these ended the interview.
    "I want to talk to someone on the SRE team before changing it.",
    "Can you put me through the question again?",
    "Hand me over the next question.",
]


@pytest.mark.parametrize("text", HUMAN_REQUESTS, ids=HUMAN_REQUESTS)
def test_asking_for_a_person_is_heard(text):
    from zeg.withdrawal import wants_a_human

    assert wants_a_human(text), text


@pytest.mark.parametrize("text", ABOUT_COLLEAGUES, ids=ABOUT_COLLEAGUES)
def test_talking_about_colleagues_is_an_ordinary_answer(text):
    from zeg.withdrawal import wants_a_human

    assert not wants_a_human(text), text


def test_typography_does_not_decide_it():
    assert reads_as_withdrawal("I’d like to stop.")
    assert reads_as_withdrawal("I’d rather you didn’t record this.")
