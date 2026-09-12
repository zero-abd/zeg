"""Adversarial probes at the consent gate.

Consent decides whether a call happens at all, and its two failure directions are not
equally bad. A false yes records someone who declined. A false no ends the interview for
someone who agreed. The first is the thing this project promised not to do, so the gate
requires a clear yes and these tests pin what "clear" means.
"""

import pytest

from zeg.backends.base import UserTranscript
from zeg.evals.consent import AFFIRMATIVE, AMBIGUOUS, REFUSAL, run_consent
from zeg.interview import Interview, reads_as_consent


def test_no_answer_is_wrongly_read_as_consent():
    r = run_consent()
    assert not r.false_yes, r.render()


def test_no_agreement_is_wrongly_read_as_refusal():
    r = run_consent()
    assert not r.false_no, r.render()


@pytest.mark.parametrize("a", AFFIRMATIVE, ids=lambda a: a.text or "empty")
def test_a_clear_yes_is_accepted(a):
    assert reads_as_consent(a.text), a.note or a.text


@pytest.mark.parametrize("a", REFUSAL, ids=lambda a: a.text or "empty")
def test_a_refusal_is_never_consent(a):
    assert not reads_as_consent(a.text), a.note or a.text


@pytest.mark.parametrize("a", AMBIGUOUS, ids=lambda a: a.text or "empty")
def test_anything_less_than_clear_is_not_consent(a):
    assert not reads_as_consent(a.text), a.note or a.text


# --- the cases that were wrong -------------------------------------------------


def test_a_yes_inside_a_hedge_is_not_a_yes():
    """'I'm not sure, yes maybe' contains an agreement word and is not one. This one
    recorded someone who had not agreed."""
    assert not reads_as_consent("I'm not sure, yes maybe?")


def test_reluctance_is_not_agreement():
    assert not reads_as_consent("well, okay, I guess")
    assert not reads_as_consent("I suppose, if I have to")


def test_english_idioms_that_contain_a_refusal_word_still_mean_yes():
    """Reading 'no problem' literally ends the call on someone who just agreed."""
    assert reads_as_consent("ok, no problem")
    assert reads_as_consent("no worries, go ahead")
    assert reads_as_consent("I don't mind at all")


def test_a_question_back_is_not_an_answer():
    assert not reads_as_consent("what happens to the recording?")
    assert not reads_as_consent("does it have to be?")


def test_silence_is_not_agreement():
    assert not reads_as_consent("")
    assert not reads_as_consent("hmm")


def test_agreement_then_refusal_is_a_refusal():
    assert not reads_as_consent("yes I understand, but I'd rather not be recorded")


# --- through the interview -------------------------------------------------------


def test_an_idiomatic_yes_lets_the_interview_proceed():
    iv = Interview()
    iv.start()
    iv.on_event(UserTranscript("no problem, go ahead", final=True), 5)
    assert iv.record.consent is True
    assert iv.record.ended is None


def test_a_hedge_ends_the_call_and_routes_to_a_human():
    iv = Interview()
    iv.start()
    iv.on_event(UserTranscript("I guess so", final=True), 5)
    assert iv.record.consent is False
    assert iv.record.ended == "consent declined"
