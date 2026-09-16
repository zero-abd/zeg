"""A candidate asking to stop, once the interview is under way.

Consent is not a gate you pass once. Someone who agreed at the start can change their
mind, and an agent that keeps asking questions and keeps recording after being asked to
stop is doing the thing the consent gate exists to prevent.

The two failure directions are not equally bad, and they are not the same as the consent
gate's. A missed withdrawal keeps recording somebody who asked us to stop. A false one
ends an interview that was going fine, which is rude and costs a candidate. The first is
worse, so the patterns lean towards ending the call.

But this runs on every answer in a technical interview, where people say "we stopped the
retries" and "we had to cancel the call to the payments API" without meaning anything of
the kind. So the patterns are narrow on purpose: a stop aimed at the recording, at the
interview, or at this call, rather than any use of the word. What is not caught is a
candidate who never says any of it plainly, and no word list fixes that.
"""

import re

from .textnorm import fold

#: Stopping something that is plainly the recording of this conversation, rather than
#: any recording: "the recording", "recording me", "being recorded".
_RECORDING = re.compile(
    r"\b(stop|end|cancel|delete|erase|turn off|switch off|shut off)\b[^.?!]{0,40}"
    r"\b(the|this|that) recording\b"
    r"|\bstop recording\s+(me|this|us|the call|the interview)\b"
    r"|\bdo ?n'?t record\s+(me|this|us)\b"
    r"|\b(not|no longer) (want to be|wish to be|comfortable being|happy being) recorded\b"
    r"|\bi'?d rather (you )?(did ?n'?t|not) record\b"
    r"|\btake me off the recording\b",
    re.I,
)

#: "stop" with nothing being stopped. "I want to stop guessing and measure it" and "we
#: stop the retries" are answers, not withdrawals, and both ended the interview until
#: this said so: no gerund after it, no object after it.
_BARE_STOP = (
    r"stop\b(?!\s+(\w+ing\b|the\b|a\b|an\b|my\b|our\b|its\b|it\b|that\b|those\b"
    r"|these\b|them\b|this\s+\w))"
)

#: Stopping the interview itself, said plainly.
_CALL = re.compile(
    r"\b(i|we)\s+(want|need|would like)\s+to\s+" + _BARE_STOP
    + r"|\bcan (we|you)\s+" + _BARE_STOP
    + r"|\bplease\s+" + _BARE_STOP
    # "cancel the call to the payments API" is a sentence about work. The interview is
    # not something you cancel *to* anything.
    + r"|\b(stop|end|cancel)\s+(the|this)\s+(interview|call)\b(?!\s+to\b)"
    r"|\bi (withdraw|revoke)\b"
    r"|\bi (no longer|do ?n'?t|do not) consent\b"
    r"|\bi'?d like to (end\b|" + _BARE_STOP + r")",
    re.I,
)


def reads_as_withdrawal(text: str) -> bool:
    """True when the candidate is asking to stop the recording or the interview."""
    plain = fold(text)
    return bool(_RECORDING.search(plain) or _CALL.search(plain))
