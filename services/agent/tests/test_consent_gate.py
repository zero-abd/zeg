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


# --- negated and conditional agreement ----------------------------------------------


def test_a_negated_agreement_is_a_refusal():
    """Each contains a word from the agreement list, and each was read as consent."""
    for text in ["Absolutely not.", "Of course not.", "Not okay.", "I'm not okay with that."]:
        assert not reads_as_consent(text), text


def test_a_condition_on_the_recording_is_not_a_clear_yes():
    """Each agrees to the call and refuses the recording, and each was read as consent."""
    assert not reads_as_consent("Of course, but can we skip the recording?")
    assert not reads_as_consent("Sure thing, but I object to being recorded.")


def test_a_condition_about_something_other_than_the_recording_is_still_a_yes():
    """The contrast rule only applies to the recording, because a false no costs the
    candidate their interview."""
    assert reads_as_consent("Yes, but please be quick.")
    assert reads_as_consent("Sure, why not.")


def test_an_instruction_to_skip_the_recording_is_not_consent():
    """No contrast word, so the conditional rule missed it, and it was read as consent."""
    assert not reads_as_consent("Sure, skip the recording.")
    assert not reads_as_consent("Yeah, stop recording please.")
    assert not reads_as_consent("Okay, don't bother recording.")


def test_a_genuine_yes_that_mentions_the_recording_is_still_a_yes():
    """Refusing every mention of recording unless it named an affirmation would have
    turned both of these into refusals. A word list against the recording does not."""
    assert reads_as_consent("Sure, it's fine if you record.")
    assert reads_as_consent("Yeah, record whatever you need.")


@pytest.mark.xfail(strict=True, reason="a condition that never mentions recording is "
                   "invisible to a rule keyed on the word")
def test_a_retention_condition_that_never_says_record_is_not_consent():
    assert not reads_as_consent("Sure, as long as nothing is saved.")
