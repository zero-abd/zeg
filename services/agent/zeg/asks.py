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


def asks_about_consent(text: str):
    """Which kind of question this is, or None if it is not one we answer."""
    plain = fold(text)
    for kind, pattern in _KINDS:
        if pattern.search(plain):
            return kind
    return None
