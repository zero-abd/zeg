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


# --- agreement that never says yes ---------------------------------------------------


def test_plain_agreement_without_a_yes_word_is_consent():
    """Each was read as a refusal, and each ended the interview for someone who agreed."""
    for text in ["Alright.", "Sounds good.", "I agree.", "I consent.", "Works for me.", "Fine."]:
        assert reads_as_consent(text), text


def test_the_negation_of_each_plain_agreement_is_still_a_refusal():
    """Widening the agreement list must not widen what gets recorded."""
    for text in ["Not alright.", "That doesn't sound good.", "I don't agree.",
                 "I do not consent.", "That doesn't work for me.", "Not fine.",
                 "I disagree.", "I can't agree to that.", "I won't consent to that."]:
        assert not reads_as_consent(text), text


def test_plain_agreement_lets_the_interview_proceed():
    iv = Interview()
    iv.start()
    iv.on_event(UserTranscript("Sounds good.", final=True), 5)
    assert iv.record.consent is True
    assert iv.record.ended is None


def test_a_backchannel_is_still_not_consent():
    """"mm-hmm" often means yes, but not clearly enough to record someone on."""
    for text in ["Mm-hmm.", "Uh-huh.", "Right."]:
        assert not reads_as_consent(text), text


@pytest.mark.xfail(strict=True, reason="a condition that never mentions recording is "
                   "invisible to a rule keyed on the word")
def test_a_retention_condition_that_never_says_record_is_not_consent():
    assert not reads_as_consent("Sure, as long as nothing is saved.")


def test_a_stutter_does_not_turn_an_agreement_into_a_refusal():
    """"No, no, that's fine" means yes, and a recogniser writes exactly that. The first
    "no" was matched before the agreement that follows it, so the call ended."""
    assert reads_as_consent("no, no, that's fine")
    assert reads_as_consent("no no worries, go ahead")
    assert not reads_as_consent("no, no, I'd rather not"), "the stutter is not the answer"


def test_recogniser_wear_does_not_flip_a_consent_answer():
    """The corpus put through what a recogniser does to speech. A flip in either
    direction is a defect: one records someone who refused, the other ends an interview
    for someone who agreed."""
    import re

    degradations = {
        "unpunctuated": lambda t: re.sub(r"[.,;:!?]", "", t).lower(),
        "no_apostrophes": lambda t: t.replace("'", "").replace("’", ""),
        "dropped_articles": lambda t: " ".join(
            w for w in t.split() if w.lower() not in ("a", "an", "the")
        ),
        "stutter": lambda t: " ".join(t.split()[:1] + t.split()),
        "filler": lambda t: "um, " + t,
    }
    flips = []
    for name, degrade in degradations.items():
        for answer in AFFIRMATIVE:
            if not reads_as_consent(degrade(answer.text)):
                flips.append("%s lost a yes: %r" % (name, degrade(answer.text)))
        for answer in REFUSAL:
            if reads_as_consent(degrade(answer.text)):
                flips.append("%s made a no into a yes: %r" % (name, degrade(answer.text)))
    assert not flips, flips
