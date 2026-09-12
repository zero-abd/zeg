import pytest

from zeg.blocklist import ProhibitedQuestion, assert_allowed, check, is_allowed


@pytest.mark.parametrize(
    "text,category",
    [
        ("So how old are you, roughly?", "age"),
        ("What year did you graduate?", "age"),
        ("Are you married?", "family"),
        ("Do you have kids at home?", "family"),
        ("Any plans for maternity leave this year?", "pregnancy"),
        ("Where are you originally from?", "origin"),
        ("What's your native language?", "origin"),
        ("Are you a citizen?", "citizenship"),
        ("Would you need sponsorship?", "citizenship"),
        ("Do you attend church on Sundays?", "religion"),
        ("Any disability we should know about?", "health"),
        ("Have you ever been arrested?", "criminal"),
        ("What's your current salary?", "salary_history"),
        ("How much did you make at your last job?", "salary_history"),
    ],
)
def test_prohibited_questions_are_caught(text, category):
    v = check(text)
    assert v is not None, "%r should have been blocked" % text
    assert v.category == category


@pytest.mark.parametrize(
    "text",
    [
        "Tell me about the hardest bug you shipped a fix for this year.",
        "What did you personally do there, as opposed to the rest of the team?",
        "Do you remember roughly what the throughput was before and after?",
        "What did you give up to get that?",
        "We ran a single-threaded consumer, which was the bottleneck.",
        "The root cause was a single point of failure in the scheduler.",
        "Are you authorized to work in the United States?",
        "How did you debug it?",
        "What broke afterwards that you did not expect?",
    ],
)
def test_ordinary_interview_questions_pass(text):
    assert is_allowed(text), "%r should not have been blocked" % text


def test_work_authorisation_is_permitted_but_visa_category_is_not():
    assert is_allowed("Are you legally able to work in the US?")
    assert not is_allowed("What kind of visa are you on?")


def test_permitted_phrasing_cannot_shield_a_prohibited_clause():
    """A lawful clause in the same breath must not launder an unlawful one."""
    text = "Are you authorized to work here, and how old are you?"
    v = check(text)
    assert v is not None and v.category == "age"


def test_assert_allowed_returns_safe_text_and_raises_otherwise():
    assert assert_allowed("What broke?") == "What broke?"
    with pytest.raises(ProhibitedQuestion) as e:
        assert_allowed("Do you have children?")
    assert e.value.violation.category == "family"


def test_violation_renders_readably():
    s = str(check("Are you married?"))
    assert "family" in s and "married" in s
