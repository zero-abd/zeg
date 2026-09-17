

def test_a_dimension_the_call_never_reached_says_so():
    """The format asks for the topics that went uncovered "and why", and every one read
    the same. A call that stopped at a minute never reached the part that asks about
    debugging, which is not the same as a candidate who was asked and said nothing."""
    from zeg.backends.base import AgentText, UserTranscript
    from zeg.interview import Interview

    iv = Interview()
    iv.start()
    iv.on_event(UserTranscript("yes that is fine", final=True), 5)
    iv.on_event(AgentText("Tell me about a system you built.", final=True), 20)
    iv.on_event(UserTranscript("I rebuilt the billing export and cut p99 to 40 ms myself",
                               final=True), 60)
    notes = {d.dimension: d.note for d in iv.report().dimensions if d.insufficient}
    assert "before the part of the interview" in notes["debugging"]
    assert "1:00" in notes["debugging"]
    # Covered from the warm-up, which this call did reach, so the reason does not apply.
    assert "Nothing in the transcript" in notes["communication"]


def test_a_full_length_call_keeps_the_plain_reason():
    from zeg.conversation import TranscriptEntry as T
    from zeg.report import assemble_report

    a = assemble_report(
        [T(0, "agent", "Tell me about it."), T(870, "caller", "we did various things")],
        consent=True, interview_started_s=5, wrapped_up_s=810,
    )
    notes = [d.note for d in a.dimensions if d.insufficient]
    assert notes and all("before the part of the interview" not in n for n in notes)
