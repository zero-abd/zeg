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


def test_a_call_that_was_cut_short_says_so():
    """Every failure path ends the call with what was gathered, which is right. A score
    from four minutes of a fifteen-minute interview then reads like a whole one."""
    call = a_call([])
    call.ended = "backend failed: could not open a new session"
    call.errors = ["could not open a new session: the runtime refused the connection"]

    report = report_for(call)
    assert any("interview is incomplete" in f for f in report.flags)
    assert any("could not open a new session" in f for f in report.flags)
    rendered = report.render()
    assert "Flags, for a human to weigh" in rendered
    assert "incomplete" in rendered


def test_a_finished_call_is_not_flagged_as_incomplete():
    call = a_call([])
    call.wrapped_up_s = 810.0
    call.ended = "time limit reached"
    assert not [f for f in report_for(call).flags if "incomplete" in f]


def test_a_declined_call_is_not_flagged_as_incomplete():
    """There was no interview to cut short."""
    call = a_call([])
    call.consent = False
    call.ended = "consent declined"
    assert not [f for f in report_for(call).flags if "incomplete" in f]


def test_a_real_call_cut_short_by_the_backend_is_flagged():
    """End to end: the backend refuses a second session partway through, the runner
    returns what it has, and the report says the interview did not finish."""
    from zeg.backends import MockBackend
    from zeg.conversation import CallerTurn, InterviewRunner
    from zeg.interview import Interview
    from zeg.memory import RolloverPolicy

    class RefusesTheSecondSession(MockBackend):
        def __init__(self):
            super().__init__()
            self.starts = 0

        def start_session(self, system_prompt, greeting=None):
            self.starts += 1
            if self.starts > 1:
                raise RuntimeError("the speech runtime refused the connection")
            return super().start_session(system_prompt, greeting=greeting)

    caller = [CallerTurn("yes that is fine", speak_s=1.5)] + [
        CallerTurn("we cut reconciler p99 from 400ms to 30ms because of a double read",
                   speak_s=8.0, pause_after_s=2.0)
    ] * 8
    interview = Interview(rollover=RolloverPolicy(context_horizon_s=20, min_session_s=10))
    result = InterviewRunner(RefusesTheSecondSession(), interview=interview).run(caller)

    assert result.failed, "the call was not cut short, so this proves nothing"
    report = report_for(result)
    assert any("interview is incomplete" in f for f in report.flags), report.flags
    assert any("refused the connection" in f for f in report.flags)


def test_the_report_still_only_scores_the_interview():
    """Flags travel with the report; the window still decides what is scored."""
    call = a_call([])
    call.interview_started_s = 22  # everything before the last question is outside it
    assert report_for(call).overall is None
