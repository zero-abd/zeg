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


def is_hesitation(text: str) -> bool:
    """True when a reply holds no words beyond hesitation sounds, or no words at all."""
    words = re.findall(r"[a-z']+", fold(text).lower())
    return all(_HESITATION.fullmatch(w) for w in words)
