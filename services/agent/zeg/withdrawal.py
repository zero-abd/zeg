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
    # "stop the recording of logs at debug" is about logs, and ended the interview.
    r"\b(the|this|that) recording\b(?!\s+of\b)"
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
    # "stop and think", "stop me if this is too much" and "stop there, that's the gist"
    # are someone pacing an answer, and each ended the interview.
    r"|these\b|them\b|this\s+\w|and\b|me\b|there\b))"
)

#: Stopping the interview itself, said plainly.
_CALL = re.compile(
    r"\b(i|we)\s+(want|need|would like)\s+to\s+" + _BARE_STOP
    + r"|\bcan (we|you)\s+" + _BARE_STOP
    + r"|\bplease\s+" + _BARE_STOP
    # "cancel the call to the payments API" is a sentence about work. The interview is
    # not something you cancel *to* anything.
    + r"|\b(stop|end|cancel)\s+(this\s+(interview|call)|the\s+interview)\b(?!\s+to\b)"
    # "The call" is often a call in the system: "we end the call when the websocket
    # drops" ended the interview. Only asked for, it is this one.
    r"|\b(can|could) (we|you)\s+(stop|end|cancel)\s+the\s+call\b(?!\s+to\b)"
    r"|\b(please|let'?s)\s+(stop|end|cancel)\s+the\s+call\b(?!\s+to\b)"
    r"|\bi (do ?n'?t|do not) want to (continue|go on|keep going|do this)"
    r"(\s+any ?more)?\W*$"
    r"|\bi (withdraw|revoke)\b"
    r"|\bi (no longer|do ?n'?t|do not) consent\b"
    # "I'd like to end on that point" closes an answer, not the interview.
    r"|\bi'?d like to (end\b(?!\s+(on|with)\b)|" + _BARE_STOP + r")",
    re.I,
)


#: Asking for a person instead. Not a complaint about the agent: it is a request to end
#: this call and route to a human, and the disclosure promises exactly that. The opening
#: verb is required, so "we talk to the payments team every week" stays an answer.
_HUMAN = re.compile(
    r"\b(can|could|may) i\b[^.?!]{0,30}\b(speak|talk)\b[^.?!]{0,20}"
    r"\b(person|human|someone|somebody|recruiter)\b"
    r"|\bi'?d (rather|prefer)\b[^.?!]{0,30}\b(person|human|recruiter)\b"
    r"|\bi would (rather|prefer)\b[^.?!]{0,30}\b(person|human|recruiter)\b"
    # The person was optional here, so "I want to talk to someone on the SRE team" was a
    # request to end the call. Someone on, from or at somewhere is a colleague.
    r"|\bi want to (speak|talk) to (a|an|some)\w*\b[^.?!]{0,20}"
    r"\b(person|human|recruiter|(someone|somebody)(?!\s+(on|from|at|in|about)\b))\b"
    r"|\bis there (a|an) (real )?(person|human|recruiter)\b"
    r"|\bis there (someone|somebody|anyone|anybody)\b[^.?!]{0,20}\b(talk|speak)\b"
    # Only to someone, or at the end: "put me through the question again" is not this.
    r"|\b(put me through|transfer me|hand me over)(\s+to\b|\s*(please)?\W*$)",
    re.I,
)


def reads_as_withdrawal(text: str) -> bool:
    """True when the candidate is asking to stop the recording or the interview."""
    plain = fold(text)
    return bool(_RECORDING.search(plain) or _CALL.search(plain))


def wants_a_human(text: str) -> bool:
    """True when the candidate is asking to speak to a person instead.

    The disclosure offers this, so an agent that hears it and asks its next question is
    breaking a promise it made in its first sentence.
    """
    return bool(_HUMAN.search(fold(text)))
