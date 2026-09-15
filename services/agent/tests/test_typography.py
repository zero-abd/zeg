"""How a character was typed must never change a compliance decision.

Both gates that match on words are regular expressions written with keyboard apostrophes
and ordinary spaces, and neither folded its input. With a typographic apostrophe,
"Yes, but I'd rather you didn't record this" counted as consent and "What's your
nationality?" was allowed to be spoken. With non-breaking spaces every multi-word
prohibited question got through, "How old are you?" included.

Every probe in the existing red-team suites is replayed here in typographic form and
must reach exactly the decision its plain form is labelled with.
"""

import pytest

from zeg.blocklist import check
from zeg.evals.consent import ALL as CONSENT_ANSWERS
from zeg.evals.redteam import ALLOWED, PROHIBITED
from zeg.interview import reads_as_consent
from zeg.textnorm import fold

TYPOGRAPHIC_APOSTROPHE = "’"
NON_BREAKING_SPACE = " "


def typographic(text):
    return text.replace("'", TYPOGRAPHIC_APOSTROPHE).replace(" ", NON_BREAKING_SPACE)


# --- every red-team probe, typed typographically ----------------------------------


@pytest.mark.parametrize("probe", PROHIBITED, ids=lambda p: p.text[:40])
def test_a_prohibited_question_is_blocked_however_it_is_typed(probe):
    v = check(typographic(probe.text))
    assert v is not None, "let through when typed typographically: %r" % probe.text
    assert v.category == probe.category


@pytest.mark.parametrize("probe", ALLOWED, ids=lambda p: p.text[:40])
def test_an_ordinary_question_is_allowed_however_it_is_typed(probe):
    assert check(typographic(probe.text)) is None


@pytest.mark.parametrize("answer", CONSENT_ANSWERS, ids=lambda a: a.text[:40] or "silence")
def test_a_consent_answer_means_the_same_however_it_is_typed(answer):
    assert reads_as_consent(typographic(answer.text)) is answer.consents


# --- the two that got through ------------------------------------------------------


def test_the_refusal_that_was_recorded_as_consent():
    assert reads_as_consent("Yes, but I’d rather you didn’t record this.") is False


def test_the_question_that_was_let_through():
    v = check("What’s your nationality?")
    assert v is not None and v.category == "origin"


# --- the folding itself ------------------------------------------------------------


@pytest.mark.parametrize("raw,folded", [
    ("I’d", "I'd"),
    ("I‘d", "I'd"),
    ("Iʼd", "I'd"),
    ("I＇d", "I'd"),
    ("“quoted”", '"quoted"'),
    ("how old are you", "how old are you"),
    ("  spaced \n out\t", "spaced out"),
    ("plain text stays plain", "plain text stays plain"),
])
def test_fold_makes_typography_plain(raw, folded):
    assert fold(raw) == folded
