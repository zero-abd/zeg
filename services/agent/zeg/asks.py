"""Questions a candidate asks instead of answering the consent request.

"What happens to the recording?" is not a refusal. It is the question of somebody
deciding, and every one of these used to end the interview: the gate wanted a clear yes,
found none, and played the line written for a refusal — "That is completely fine" — at a
candidate who had not refused anything.

The gate itself does not change. Silence is still not agreement and a hedge is still not
a yes. What changes is what happens to a question: it gets an answer and the consent
request comes again.

Only the four kinds we can answer honestly are recognised. Anything else falls through to
the gate, because an agent that improvises an answer about what happens to a recording is
worse than one that hands the call to a person.
"""

import re

from .textnorm import fold

#: What happens to the recording, who hears it, how long it is kept.
_RECORDING = re.compile(
    r"\bwhat happens\b|\bwhat do you do with (it|this|the recording)\b"
    r"|\bwho (gets to |can |will )?(see|hear|listen|review)\b"
    r"|\bhow long (do you|is it|will it)\b"
    r"|\bis (it|this|the recording) (kept|stored|shared|deleted|saved)\b"
    r"|\bwhere (is|does) (it|this) (go|end up|get stored|kept)\b",
    re.I,
)

#: Did not catch the question.
_REPEAT = re.compile(
    r"\b(can|could|would) you (repeat|say that again)\b|\bsay that again\b"
    r"|\bwhat was the question\b|\bsorry,? what\b|\bcome again\b"
    r"|\bi did ?n'?t (catch|hear|get) that\b|\brepeat that\b",
    re.I,
)

#: Whether they are talking to a person. Answered yes-immediately by policy.
_AI = re.compile(
    r"\bare you (an? )?(real |actual )?(person|human|bot|robot|machine|ai)\b"
    r"|\bam i (talking|speaking) (to|with) (an? )?(real )?(person|human|bot|robot|machine|ai)\b"
    r"|\bis this (an? )?(bot|robot|recording|real person|human)\b"
    r"|\bare you real\b",
    re.I,
)

#: Whether the recording is required at all.
_NECESSITY = re.compile(
    r"\bdoes it have to be\b|\bdo i have to\b|\bdo we have to\b"
    r"|\bis (it|that) (required|mandatory|necessary|compulsory)\b"
    r"|\bcan we do (it|this) without\b|\bdo you have to record\b"
    r"|\bis there a way (to|not to)\b",
    re.I,
)

#: Checked in this order. A question about the recording that also asks whether it is
#: required is answered as the harder of the two: whether it can be skipped.
_KINDS = (
    ("ai", _AI),
    ("necessity", _NECESSITY),
    ("recording", _RECORDING),
    ("repeat", _REPEAT),
)


#: A question form at the start of a turn, after an optional "sorry," or "so". "What I did
#: was rewrite it" is not one: the word after "what" has to be a verb for it to ask.
_QUESTION_OPENER = re.compile(
    r"^\s*(?:(?:sorry|so|and|but|okay|ok|actually|um|uh|quick question)[,\s]+)*"
    r"(?:(?:what|how|why|when|where|who|which)\s+"
    r"(?:is|are|was|were|does|do|did|will|would|should|can|could)\b"
    r"|(?:can|could|would|will|do|does|did|is|are)\s+"
    r"(?:you|we|i|the|this|that|it|there|your)\b)",
    re.I,
)


def is_question(text: str) -> bool:
    """True when a turn is asking rather than telling.

    Mid-interview, a question from the candidate was taken as an answer: "what does this
    team actually work on?" became a claim, and the engine told the model to ask what they
    personally did about it. Whether it also carries evidence is for the caller to check,
    because "we cut p99 to 30, right?" is an answer with a question mark on it.
    """
    plain = fold(text).strip()
    return plain.endswith("?") or bool(_QUESTION_OPENER.search(plain))


def asks_about_consent(text: str):
    """Which kind of question this is, or None if it is not one we answer."""
    plain = fold(text)
    for kind, pattern in _KINDS:
        if pattern.search(plain):
            return kind
    return None


#: Having nothing more to ask, said in a way that cannot be anything else. After the
#: wrap-up only, where the agent has just asked whether they have questions.
_NOTHING_MORE = re.compile(
    r"\b(i'?m|i am) (good|all set|all good|fine)\b(?!\s+(at|with|in|on|for)\b)"
    r"|\bthat'?s (all|it|everything)\b"
    r"|\bno (more |other |further )?questions\b"
    r"|\bnothing (else|more|from me|comes to mind)\b"
    r"|\b(do ?n'?t|do not) have (any )?(more |other |further )?(questions|anything)\b"
    r"|\bthat covers it\b",
    re.I,
)

#: A bare no, which only means "no questions" as the reply to the wrap-up itself.
_BARE_NO = re.compile(r"^\W*(no|nope|nah|not really)\b", re.I)

#: Longer than this and the candidate is saying something, even if it starts with no.
_MAX_CLOSING_WORDS = 12


def has_nothing_more(text: str, replying_to_wrap_up: bool) -> bool:
    """True when the candidate is telling us they have no more questions.

    A call past its wrap-up with nothing left to say went on, silent and recorded, until
    the time limit: measured, 76 seconds after "no, I think I'm good, thanks". A question,
    or anything long enough to be more than a closing remark, is not this.
    """
    plain = fold(text).strip()
    if not plain or is_question(plain) or len(plain.split()) > _MAX_CLOSING_WORDS:
        return False
    if _NOTHING_MORE.search(plain):
        return True
    return replying_to_wrap_up and bool(_BARE_NO.search(plain))
