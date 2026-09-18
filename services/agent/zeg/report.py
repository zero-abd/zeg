"""The report a human reads, assembled from a finished call.

One place, so every way of driving a call produces the same report: the runner, the
demo, and a driver that uses the Interview directly, as the media gateway will. The
window and the flags used to live beside the runner and the demo only. A driver holding an
Interview had `transcript_for_scoring()`, which returns everything, and scoring that scored
the consent exchange and the closing questions and dropped every compliance flag.
"""

from typing import Optional, Sequence, Tuple

from .config import CallConfig
from .engine import phase_covering
from .scoring import Assessment, Judge, score_call

_OPEN = float("inf")


def interview_window(
    interview_started_s: Optional[float], wrapped_up_s: Optional[float]
) -> Tuple[float, float]:
    """The part of the call that is the interview, for scoring.

    Consent never settled means there was no interview, so nothing is inside it.
    """
    if interview_started_s is None:
        return (_OPEN, _OPEN)
    return (interview_started_s, wrapped_up_s if wrapped_up_s is not None else _OPEN)


def assemble_report(
    transcript: Sequence,
    flags: Sequence[str] = (),
    consent: Optional[bool] = None,
    interview_started_s: Optional[float] = None,
    wrapped_up_s: Optional[float] = None,
    ended: Optional[str] = None,
    errors: Sequence[str] = (),
    judge: Optional[Judge] = None,
    call: Optional[CallConfig] = None,
) -> Assessment:
    """Score the interview and carry everything a reviewer needs to weigh it.

    The interview's own flags travel with the score. A call that had consent and never
    reached its wrap-up says it is incomplete and how it ended, because a score from four
    minutes of a fifteen-minute interview otherwise reads like a whole one. Anything that
    failed during the call is listed.
    """
    # Failures first: a call that died is the thing a reviewer has to weigh before
    # anything the score says about the candidate. They were listed after the compliance
    # flags and before the scorer's own, so the one fact that was nobody's fault sat in
    # the middle of a list about the candidate.
    out = ["Something failed during the call: %s" % error for error in errors]
    out.extend(flags)
    incomplete = ""
    if consent and wrapped_up_s is None:
        incomplete = "the call ended before the wrap-up"
        out.append(
            "The call ended before the wrap-up, so the interview is incomplete: %s."
            % (ended or "it stopped early")
        )
    if errors and not incomplete:
        incomplete = "something failed during the call"
    assessment = score_call(
        transcript,
        judge=judge,
        flags=out,
        window=interview_window(interview_started_s, wrapped_up_s),
    )
    assessment.incomplete = incomplete
    _say_why_uncovered(assessment, call)
    return assessment


def _say_why_uncovered(assessment: Assessment, call: Optional[CallConfig]) -> None:
    """Name the reason a dimension has none, where the plan gives one.

    The format asks for the topics that went uncovered "and why", and every one of them
    read the same: nothing in the transcript speaks to this. A call that ended at four
    minutes never reached the part that asks about debugging, which is a different thing
    from a candidate who was asked and said nothing usable.
    """
    for scored in assessment.dimensions:
        if not scored.insufficient:
            continue
        phase, starts_at = phase_covering(scored.dimension, call)
        if phase is None or assessment.duration_s >= starts_at:
            continue
        mins, secs = divmod(int(assessment.duration_s), 60)
        scored.note = (
            "The call ended at %d:%02d, before the part of the interview that asks about "
            "this. Not a low score." % (mins, secs)
        )
