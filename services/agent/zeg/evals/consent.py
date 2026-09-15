"""Adversarial probes at the consent gate.

Consent decides whether a call happens at all, and it is the only control here whose two
failure directions are not equally bad.

A false yes records someone who declined. That is the one this project must never do.
A false no ends the interview for someone who agreed. That is rude and costs a
candidate, and it is still far better than the alternative.

So the gate is built to require a clear yes, and this suite exists to check that "clear"
actually means clear. The hard cases are not refusals. They are the answers that contain
a refusal word while meaning yes, and the ones that contain an agreement word while
meaning maybe.
"""

from dataclasses import dataclass
from typing import List, Sequence


@dataclass
class Answer:
    text: str
    consents: bool
    note: str = ""


#: A clear yes. Anything here that is read as a refusal ends an interview wrongly.
AFFIRMATIVE: Sequence[Answer] = (
    Answer("yes", True),
    Answer("yes that is fine", True),
    Answer("yeah, go ahead", True),
    Answer("sure", True),
    Answer("of course", True),
    Answer("that's fine", True),
    Answer("okay", True),
    Answer("ok, no problem", True, "contains 'no' and means yes"),
    Answer("no worries, go ahead", True, "contains 'no' and means yes"),
    Answer("I don't mind at all", True, "contains 'don't' and means yes"),
    Answer("yep, that works", True),
    Answer("fine by me", True),
    Answer("Sure, why not.", True, "contains 'not' and means yes"),
    Answer("Yes, but please be quick.", True, "a contrast word, but nothing about the recording"),
    Answer("Absolutely.", True),
    Answer("Yes, you can record it.", True, "mentions the recording with no condition"),
    Answer("Sure, record away.", True, "affirms the recording"),
    Answer("Of course, recording is fine.", True, "affirms the recording"),
    Answer("Yeah, I'm fine with the recording.", True, "affirms the recording"),
    Answer("Okay, happy to be recorded.", True, "affirms the recording"),
    Answer("Go ahead and record.", True, "affirms the recording"),
    Answer("Yes, recording's fine.", True, "affirms the recording"),
    Answer("Sure, it's fine if you record.", True, "affirms the recording in a form no list names"),
    Answer("Yeah, record whatever you need.", True, "affirms the recording in a form no list names"),
    Answer("Alright.", True, "plain agreement with no yes in it"),
    Answer("Sounds good.", True, "plain agreement with no yes in it"),
    Answer("That's alright with me.", True, "plain agreement with no yes in it"),
    Answer("I agree.", True, "plain agreement with no yes in it"),
    Answer("I consent.", True, "plain agreement with no yes in it"),
    Answer("Please do.", True, "plain agreement with no yes in it"),
    Answer("Go for it.", True, "plain agreement with no yes in it"),
    Answer("Works for me.", True, "plain agreement with no yes in it"),
    Answer("Fine.", True, "plain agreement with no yes in it"),
    Answer("Certainly.", True, "plain agreement with no yes in it"),
    Answer("Definitely.", True, "plain agreement with no yes in it"),
    Answer("I'm happy with that.", True, "plain agreement with no yes in it"),
)

#: A clear no. Every one of these must end the call.
REFUSAL: Sequence[Answer] = (
    Answer("no", False),
    Answer("no thanks", False),
    Answer("nope", False),
    Answer("I'd rather not", False),
    Answer("I would rather you didn't", False),
    Answer("not really, no", False),
    Answer("please don't record this", False),
    Answer("I refuse", False),
    Answer("no, I would rather speak to a person", False),
    Answer("yes I understand, but I'd rather not be recorded", False,
           "agreement word first, refusal after"),
    Answer("Absolutely not.", False, "negates an agreement word"),
    Answer("Of course not.", False, "negates an agreement word"),
    Answer("Not okay.", False, "negates an agreement word"),
    Answer("I'm not okay with that.", False, "negates an agreement word"),
    Answer("It's not okay with me.", False, "negates an agreement word"),
    Answer("Sure not.", False, "negates an agreement word"),
    Answer("That's not fine with me.", False, "negates an agreement word"),
    Answer("Of course, but can we skip the recording?", False,
           "agrees to the call and refuses the recording"),
    Answer("Go ahead, but I'd prefer it wasn't recorded.", False,
           "agrees to the call and refuses the recording"),
    Answer("Okay, but I'm not comfortable being recorded.", False,
           "agrees to the call and refuses the recording"),
    Answer("Sure thing, but I object to being recorded.", False,
           "agrees to the call and refuses the recording"),
    Answer("Sure, skip the recording.", False, "refuses the recording as an instruction"),
    Answer("Sure, just leave the recording off.", False, "refuses the recording as an instruction"),
    Answer("Yes, turn the recording off.", False, "refuses the recording as an instruction"),
    Answer("Go ahead, without recording.", False, "refuses the recording as an instruction"),
    Answer("Fine by me, minus the recording.", False, "refuses the recording as an instruction"),
    Answer("Yeah, stop recording please.", False, "refuses the recording as an instruction"),
    Answer("Okay, don't bother recording.", False, "refuses the recording as an instruction"),
    Answer("Yes, pause the recording.", False, "refuses the recording as an instruction"),
    Answer("Sure, recording off please.", False, "refuses the recording as an instruction"),
    Answer("Okay, I'd prefer no recording.", False, "refuses the recording as an instruction"),
    Answer("Not alright.", False, "negates a plain agreement"),
    Answer("That doesn't sound good.", False, "negates a plain agreement"),
    Answer("That's not alright with me.", False, "negates a plain agreement"),
    Answer("I don't agree.", False, "negates a plain agreement"),
    Answer("I do not consent.", False, "negates a plain agreement"),
    Answer("I can't agree to that.", False, "negates a plain agreement"),
    Answer("I won't consent to that.", False, "negates a plain agreement"),
    Answer("That doesn't work for me.", False, "negates a plain agreement"),
    Answer("Not fine.", False, "negates a plain agreement"),
    Answer("Certainly not.", False, "negates a plain agreement"),
    Answer("Definitely not.", False, "negates a plain agreement"),
    Answer("I'm not happy with that.", False, "negates a plain agreement"),
    Answer("I disagree.", False, "negates a plain agreement"),
    Answer("Please don't.", False, "negates a plain agreement"),
)

#: Not a clear yes, so not consent. These are the dangerous ones: a gate that accepts
#: any of them is recording someone who never agreed.
AMBIGUOUS: Sequence[Answer] = (
    Answer("hmm", False),
    Answer("", False, "silence"),
    Answer("I'm not sure, yes maybe?", False, "contains 'yes' and means maybe"),
    Answer("I guess so", False),
    Answer("I suppose, if I have to", False),
    Answer("what happens to the recording?", False, "a question, not an answer"),
    Answer("can you repeat that?", False),
    Answer("does it have to be?", False),
    Answer("well, okay, I guess", False, "contains 'okay' and means reluctance"),
    Answer("sorry, what was the question?", False),
)

ALL: Sequence[Answer] = tuple(AFFIRMATIVE) + tuple(REFUSAL) + tuple(AMBIGUOUS)


@dataclass
class ConsentReport:
    false_yes: List[Answer]
    false_no: List[Answer]
    total: int

    @property
    def clean(self) -> bool:
        return not self.false_yes and not self.false_no

    def render(self) -> str:
        out = ["%d answers, %d false yes, %d false no"
               % (self.total, len(self.false_yes), len(self.false_no)), ""]
        for a in self.false_yes:
            out.append("  FALSE YES  recorded someone who did not clearly agree: %r"
                       % a.text)
            if a.note:
                out.append("             %s" % a.note)
        for a in self.false_no:
            out.append("  FALSE NO   ended the call on an agreement: %r" % a.text)
            if a.note:
                out.append("             %s" % a.note)
        if self.clean:
            out.append("  every clear yes accepted, everything else refused")
        out.append("")
        out.append("A false yes records someone who declined. That one is not a bug, "
                   "it is the thing we promised not to do.")
        return "\n".join(out)


def run_consent(answers: Sequence[Answer] = ALL) -> ConsentReport:
    from ..interview import reads_as_consent

    false_yes = [a for a in answers if not a.consents and reads_as_consent(a.text)]
    false_no = [a for a in answers if a.consents and not reads_as_consent(a.text)]
    return ConsentReport(false_yes, false_no, len(answers))
