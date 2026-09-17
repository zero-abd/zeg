"""The report a human reads, assembled from a finished call.

One place, so every way of driving a call produces the same report: the runner, the
demo, and a driver that uses the Interview directly, as the media gateway will. The
window and the flags used to live beside the runner and the demo only. A driver holding an
Interview had `transcript_for_scoring()`, which returns everything, and scoring that scored
the consent exchange and the closing questions and dropped every compliance flag.
"""

from typing import Optional, Sequence, Tuple

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
) -> Assessment:
    """Score the interview and carry everything a reviewer needs to weigh it.

    The interview's own flags travel with the score. A call that had consent and never
    reached its wrap-up says it is incomplete and how it ended, because a score from four
    minutes of a fifteen-minute interview otherwise reads like a whole one. Anything that
    failed during the call is listed.
    """
    out = list(flags)
    if consent and wrapped_up_s is None:
        out.append(
            "The call ended before the wrap-up, so the interview is incomplete: %s."
            % (ended or "it stopped early")
        )
    for error in errors:
        out.append("Something failed during the call: %s" % error)
    return score_call(
        transcript,
        judge=judge,
        flags=out,
        window=interview_window(interview_started_s, wrapped_up_s),
    )
