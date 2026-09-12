"""Questions the agent must never ask.

This is enforcement, not guidance. The check runs on outbound text before it reaches
synthesis, so a model that generates a prohibited question produces a blocked turn
rather than a spoken one.

It lives in code because a prompt instruction is a request and this is a requirement.
A model asked nicely to avoid these will comply almost always, and "almost always"
across thousands of candidates is a certainty of failure. See docs/06-compliance.md.

Patterns aim to catch how these questions actually get phrased while an agent is
building rapport, which is where they slip out. They will not catch every phrasing.
A missed one is a bug; a false positive costs one rephrased question and is cheap.
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

#: Explicitly permitted, checked before the block list. A single yes/no question about
#: authorisation to work is lawful in most jurisdictions; questions about citizenship,
#: visa category or national origin are not.
_ALLOWED = [
    re.compile(r"\b(authori[sz]ed|eligible|legally able)\s+to\s+work\b", re.I),
    re.compile(r"\bwork\s+authori[sz]ation\b", re.I),
]

_RULES: List[Tuple[str, str, str]] = [
    ("age", r"\bhow old are you\b|\byour age\b|\bwhat year (were you born|did you (graduate|finish))\b|\bare you (over|under)\s+\d+\b",
     "Age and proxies for it."),
    ("family", r"\bare you (married|single|engaged)\b|\bdo you have (any )?(kids|children)\b|\byour (husband|wife|spouse|partner)\b|\bplanning (on )?(a family|to have (kids|children))\b|\bchildcare\b",
     "Marital and family status."),
    ("pregnancy", r"\bpregnan\w*\b|\bmaternity\b|\bpaternity\b|\bparental leave\b",
     "Pregnancy and family-leave plans."),
    ("origin", r"\bwhere are you (really |originally )?from\b|\bwhat('s| is) your (nationality|ethnicity|race|(native|first|mother) (language|tongue))\b|\bwhere were you born\b|\byour accent\b",
     "National origin, ethnicity and proxies for them."),
    ("citizenship", r"\bare you (an? )?(citizen|permanent resident)\b|\b(your|what) citizenship\b|\bcitizenship status\b|\bdo you hold (a )?(citizenship|passport)\b|\bgreen card\b|\bvisa (status|type|category)\b|\bwhat (kind of )?visa\b|\bsponsorship\b",
     "Citizenship and immigration status beyond a single work-authorisation question."),
    ("religion", r"\bwhat (faith|religion)\b|\bare you religious\b|\bdo you (go to |attend )?(church|mosque|synagogue|temple)\b|\bobserve the sabbath\b|\breligious holidays?\b",
     "Religion and observance."),
    ("health", r"\bdisabilit\w*\b|\bmedical (conditions?|histor(y|ies)|issues?)\b|\bhealth (conditions?|issues?|problems?)\b|\bare you (on|taking) (any )?medication\b|\bmental health\b|\bhow many (sick )?days (have you|did you) (taken?|miss)\b",
     "Disability, health and medical history."),
    ("criminal", r"\b(ever been )?arrested\b|\bcriminal (record|history|background)\b|\bconvicted\b|\bfelony\b|\bmisdemeanou?r\b",
     "Arrest and conviction record."),
    ("salary_history", r"\b(current|previous|last|prior) (salary|compensation|pay|wage)\b|\bhow much (do|did|were|are|was) you\b|\b(are|were) you (currently |now )?(being )?(paid|making|earning)\b|\bwhat (are|were) you (currently )?(making|earning|paid|on)\b|\byour salary (is|was)\b",
     "Salary history, which is prohibited in many jurisdictions."),
]

_COMPILED = [(name, re.compile(pat, re.I), why) for name, pat, why in _RULES]


@dataclass(frozen=True)
class Violation:
    category: str
    matched: str
    why: str

    def __str__(self) -> str:
        return "blocked (%s): %r — %s" % (self.category, self.matched, self.why)


class ProhibitedQuestion(Exception):
    """Raised when text that must not be spoken reaches the gate."""

    def __init__(self, violation: Violation) -> None:
        super().__init__(str(violation))
        self.violation = violation


def check(text: str) -> Optional[Violation]:
    """Return the first violation in `text`, or None if it is safe to speak."""
    for allowed in _ALLOWED:
        if allowed.search(text):
            # Strip the permitted phrasing so it cannot shield a prohibited clause
            # elsewhere in the same utterance.
            text = allowed.sub(" ", text)
    for name, pattern, why in _COMPILED:
        m = pattern.search(text)
        if m:
            return Violation(name, m.group(0), why)
    return None


def is_allowed(text: str) -> bool:
    return check(text) is None


def assert_allowed(text: str) -> str:
    """Gate an outbound utterance. Returns the text, or raises."""
    v = check(text)
    if v is not None:
        raise ProhibitedQuestion(v)
    return text
