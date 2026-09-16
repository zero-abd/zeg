"""What the demo hands to a human at the end of a call.

The report is the artefact: the console output is one way of looking at it, and
anything that keeps a report rather than a terminal scrollback keeps this object.
"""

from zeg.cli import report_for
from zeg.conversation import DrivenResult, TranscriptEntry as T

TALKED_OVER = (
    "The candidate talked over the recording disclosure. It was repeated in full "
    "before consent was taken."
)
BLOCKED = "Blocked a prohibited question: blocked (age): 'how old are you'"


def a_call(flags):
    result = DrivenResult()
    result.transcript = [
        T(0, "agent", "Is that okay with you?"),
        T(5, "caller", "yes that is fine"),
        T(10, "agent", "What did you personally do there?"),
        T(15, "caller", "I wrote the advisory-lock fix because the root cause was a double read."),
        T(20, "agent", "Any numbers?"),
        T(25, "caller", "11 double-settlements over 6 weeks, down to 0 after."),
    ]
    result.flags = list(flags)
    result.consent = True
    result.interview_started_s = 5
    return result


def test_the_compliance_flags_reach_the_report():
    """They were printed beside the report and left out of it."""
    report = report_for(a_call([TALKED_OVER, BLOCKED]))
    assert TALKED_OVER in report.flags
    assert BLOCKED in report.flags
    rendered = report.render()
    assert "Flags, for a human to weigh" in rendered
    assert "talked over the recording disclosure" in rendered
    assert "Blocked a prohibited question" in rendered


def test_a_clean_call_carries_no_flags_of_its_own():
    report = report_for(a_call([]))
    assert not [f for f in report.flags if "disclosure" in f or "Blocked" in f]


def test_the_report_still_only_scores_the_interview():
    """Flags travel with the report; the window still decides what is scored."""
    call = a_call([])
    call.interview_started_s = 22  # everything before the last question is outside it
    assert report_for(call).overall is None
