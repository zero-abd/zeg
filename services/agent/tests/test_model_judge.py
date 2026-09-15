"""The judge that has a model behind it.

The model is a plain callable here, so these tests pin behaviour rather than any
particular model. The behaviour that matters most is distrust: a fabricated quote in a
hiring report is worse than no report at all.
"""

import json

import pytest

from zeg.conversation import TranscriptEntry as T
from zeg.engine import DIMENSIONS
from zeg.scoring import (
    JUDGE_PROMPT,
    ModelJudge,
    parse_verdict,
    render_units,
    score_call,
    to_qa_units,
)

TRANSCRIPT = [
    T(0, "agent", "Tell me about the hardest bug you fixed."),
    T(10, "caller", "A race in the reconciler. I wrote the advisory-lock fix."),
    T(20, "agent", "What did it cost?"),
    T(30, "caller", "Batch time roughly doubled."),
]
UNITS = to_qa_units(TRANSCRIPT)


def replying(payload):
    """A model that always answers with the same verdict."""
    def complete(prompt):
        return json.dumps(payload) if isinstance(payload, dict) else payload
    return complete


# --- parsing ------------------------------------------------------------------


def test_a_clean_verdict_parses():
    assert parse_verdict('{"score": 3, "quote": "x", "reason": "y"}') == (3, "x", "y")


def test_json_wrapped_in_prose_still_parses():
    """Models pad their answers. That is not a reason to lose the report."""
    raw = 'Sure!\n```json\n{"score": 2, "quote": "x", "reason": "y"}\n```\nHope that helps'
    assert parse_verdict(raw)[0] == 2


def test_a_null_score_is_a_valid_verdict():
    assert parse_verdict('{"score": null, "quote": null, "reason": "nothing"}')[0] is None


@pytest.mark.parametrize("raw", [
    "not json at all",
    "",
    '{"score": 9, "quote": "x"}',        # outside the rubric
    '{"score": "three", "quote": "x"}',  # not a number
    '{"score": 0, "quote": "x"}',        # below the rubric
    '["score", 3]',                      # not an object
    '{"score": 3, "quote": 42}',         # quote is not text
])
def test_unreadable_or_out_of_range_output_is_rejected(raw):
    """A guess here becomes a number in a hiring report."""
    assert parse_verdict(raw) is None


def test_a_non_string_reply_is_rejected():
    assert parse_verdict(None) is None


# --- the fabrication guard -----------------------------------------------------


def test_a_real_quote_is_accepted_and_timestamped():
    j = ModelJudge(replying({"score": 3, "quote": "I wrote the advisory-lock fix",
                             "reason": "first person and specific"}))
    d = j.score_dimension("ownership", UNITS)
    assert d.score == 3
    assert d.evidence[0].at_s == 10
    assert not j.fabrications


def test_a_fabricated_quote_voids_the_score():
    """The score might be right. It is not usable without a citation, and a citation
    that cannot be located is the one thing a report must never carry."""
    j = ModelJudge(replying({"score": 4, "quote": "I single-handedly rewrote Kubernetes",
                             "reason": "impressive"}))
    d = j.score_dimension("ownership", UNITS)
    assert d.insufficient
    assert "not present in the transcript" in d.note
    assert j.fabrications == ["ownership"]


def test_a_score_with_no_quote_at_all_is_void():
    j = ModelJudge(replying({"score": 4, "quote": None, "reason": "vibes"}))
    assert j.score_dimension("ownership", UNITS).insufficient


def test_whitespace_and_case_differences_are_not_fabrication():
    j = ModelJudge(replying({"score": 3, "quote": "i  WROTE the   advisory-lock fix",
                             "reason": "ok"}))
    assert j.score_dimension("ownership", UNITS).score == 3


def test_a_quote_from_the_interviewer_is_not_evidence_about_the_candidate():
    """This used to be accepted, on purpose. The quote is in the transcript, but the
    candidate never said it, and a report citing it scores the candidate on the
    interviewer's words."""
    j = ModelJudge(replying({"score": 2, "quote": "What did it cost?", "reason": "ok"}))
    assert j.score_dimension("tradeoffs", UNITS).insufficient
    assert j.fabrications == ["tradeoffs"]


@pytest.mark.parametrize("quote", [
    "I wrote the advisory-lock.",              # a full stop the transcript does not have
    "a race in the reconciler, I wrote",      # a comma where the transcript has a stop
    "“I wrote the advisory-lock fix”",  # wrapped in typographic quote marks
])
def test_punctuation_a_judge_adds_is_not_fabrication(quote):
    """Each is word for word what the candidate said, and each voided the score."""
    j = ModelJudge(replying({"score": 3, "quote": quote, "reason": "ok"}))
    assert j.score_dimension("ownership", UNITS).score == 3, quote


def test_a_straight_apostrophe_matches_a_curly_one_in_the_transcript():
    units = to_qa_units([T(0, "agent", "Why?"), T(5, "caller", "I didn’t trust the retry path")])
    j = ModelJudge(replying({"score": 3, "quote": "I didn't trust the retry path", "reason": "ok"}))
    d = j.score_dimension("debugging", units)
    assert d.score == 3
    assert d.evidence[0].at_s == 5


@pytest.mark.parametrize("quote", [
    "I wrote the lock fix",      # a word missing
    "rote the advisory-lock",   # starts inside a word
    "I didnt write the fix",     # words the candidate never said
])
def test_what_is_still_fabrication(quote):
    j = ModelJudge(replying({"score": 3, "quote": quote, "reason": "ok"}))
    assert j.score_dimension("ownership", UNITS).insufficient, quote


def test_the_interviewers_phrasing_cannot_score_ownership():
    units = to_qa_units([
        T(0, "agent", "What did you personally do, as opposed to the team?"),
        T(5, "caller", "the team handled most of it, I was mostly watching"),
    ])
    j = ModelJudge(replying({"score": 4, "quote": "you personally do", "reason": "owns it"}))
    assert j.score_dimension("ownership", units).insufficient


# --- failure modes --------------------------------------------------------------


def test_a_judge_that_raises_does_not_take_the_report_with_it():
    def boom(prompt):
        raise RuntimeError("out of memory")

    d = ModelJudge(boom).score_dimension("ownership", UNITS)
    assert d.insufficient and "Judge failed" in d.note


def test_unreadable_output_becomes_insufficient_not_a_guess():
    d = ModelJudge(replying("I think probably a 3?")).score_dimension("ownership", UNITS)
    assert d.insufficient


def test_an_empty_transcript_is_not_sent_to_the_model():
    calls = []

    def spy(prompt):
        calls.append(prompt)
        return "{}"

    ModelJudge(spy).score_dimension("ownership", [])
    assert calls == []


# --- the prompt -----------------------------------------------------------------


def test_the_prompt_carries_the_dimension_and_the_transcript():
    seen = {}

    def spy(prompt):
        seen["p"] = prompt
        return json.dumps({"score": None, "quote": None, "reason": "none"})

    ModelJudge(spy).score_dimension("technical_depth", UNITS)
    assert "technical depth" in seen["p"]
    assert "advisory-lock" in seen["p"]


def test_the_communication_prompt_excludes_accent_and_fluency():
    """The most likely route to a discriminatory score is scoring how someone sounds."""
    seen = {}

    def spy(prompt):
        seen["p"] = prompt
        return json.dumps({"score": None, "quote": None, "reason": "none"})

    ModelJudge(spy).score_dimension("communication", UNITS)
    assert "Accent" in seen["p"] and "must not affect" in seen["p"]


def test_the_prompt_tells_the_model_a_null_is_a_real_answer():
    assert "null is not a low score" in JUDGE_PROMPT


def test_rendered_units_label_both_speakers():
    r = render_units(UNITS)
    assert "Interviewer:" in r and "Candidate:" in r


# --- through the whole pass -------------------------------------------------------


def test_one_model_call_per_dimension():
    calls = []

    def spy(prompt):
        calls.append(prompt)
        return json.dumps({"score": 3, "quote": "Batch time roughly doubled",
                           "reason": "ok"})

    score_call(TRANSCRIPT, judge=ModelJudge(spy))
    assert len(calls) == len(DIMENSIONS)


def test_a_model_that_fabricates_everything_yields_insufficient_signal():
    j = ModelJudge(replying({"score": 4, "quote": "nothing like this was said",
                             "reason": "great"}))
    a = score_call(TRANSCRIPT, judge=j)
    assert a.band == "insufficient signal"
    assert a.overall is None
