"""What counts as a candidate hesitating rather than answering.

The client ends a turn after 640 ms of silence, so "um" and a pause arrive as a complete
reply. The interview must not take that as consent refused or as an answer to a probe,
and scoring must not pair it with a question as though it answered one. One definition,
shared, so those three cannot disagree.

"mm-hmm" and "uh-huh" are left out on purpose. They often mean yes, so they are judged
like any other reply rather than waited through.
"""

import re

from .textnorm import fold

_HESITATION = re.compile(r"(u+m+|u+h+|e+r+m*|a+h+|h+m+|well|so)", re.I)

#: Asking for time. Said to the consent question, "hmm, let me think" was read as not
#: agreeing, and the call was ended as declined on someone who was still deciding.
_ASKING_FOR_TIME = (
    r"\b(let me (think|see)|give me a (sec|second|moment|minute)|hold on|one sec(ond)?"
    r"|good question|that's a good one)\b"
)


def is_hesitation(text: str) -> bool:
    """True when a reply holds no words beyond hesitation sounds and asking for time, or
    no words at all."""
    plain = re.sub(_ASKING_FOR_TIME, " ", fold(text).lower())
    words = re.findall(r"[a-z']+", plain)
    return all(_HESITATION.fullmatch(w) for w in words)


#: Words a finished sentence does not end on. Deliberately short: "that", "so", "to",
#: "then" and "on" all end ordinary sentences ("I think so", "back then", "turned it on").
_TRAILING = re.compile(r"(u+m+|u+h+|e+r+m*|a+h+|h+m+|and|but|or|because|cause|the|a|an|if|although)")

#: Asking for time, at the end of what has been said so far.
_THINKING = re.compile(_ASKING_FOR_TIME + r"\W*$", re.I)


def sounds_unfinished(text: str) -> bool:
    """True when what has been heard so far stops mid-thought.

    Only the pure hesitation was held, so "uh, let me think" and "so the reason was, uh"
    committed at the ordinary pause and the model answered someone still thinking.
    """
    plain = fold(text).lower()
    if _THINKING.search(plain):
        return True
    words = re.findall(r"[a-z']+", plain)
    return bool(words) and bool(_TRAILING.fullmatch(words[-1]))
