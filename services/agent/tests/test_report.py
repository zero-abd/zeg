

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


def test_the_report_carries_the_transcript_so_a_quote_can_be_checked():
    """A driver that keeps only the report, as the media gateway will, had no way to show
    a quote in its place or let a reviewer check one."""
    from zeg.backends.base import AgentText, UserTranscript
    from zeg.interview import Interview

    iv = Interview()
    iv.start()
    iv.on_event(UserTranscript("yes that is fine", final=True), 5)
    iv.on_event(AgentText("What did you personally do?", final=True), 20)
    iv.on_event(UserTranscript("I wrote the advisory-lock fix myself", final=True), 40)
    report = iv.report()

    rendered = report.render_transcript()
    assert "[00:40] Candidate   I wrote the advisory-lock fix myself" in rendered
    assert "Interviewer" in rendered
    for scored in report.dimensions:
        for evidence in scored.evidence:
            assert evidence.quote in rendered, "a cited quote must be checkable"


def test_the_one_page_report_does_not_become_the_transcript():
    """Collapsed means the reviewer asks for it. One page is the format."""
    from zeg.conversation import TranscriptEntry as T
    from zeg.report import assemble_report

    a = assemble_report(
        [T(0, "agent", "Tell me about it."), T(30, "caller", "I wrote the lock fix myself")],
        consent=True, interview_started_s=0,
    )
    assert "Tell me about it." not in a.render()
    assert "Tell me about it." in a.render_transcript()


def _mixed_call():
    from zeg.conversation import TranscriptEntry as T

    return [
        T(0, "agent", "What did you personally do?"),
        T(30, "caller", "I wrote the advisory-lock fix myself because the root cause was "
                        "a double read, and p99 dropped from 900 ms to 40 ms"),
        T(60, "agent", "What did you give up to get that?"),
        T(80, "caller", "we basically did various things around that"),
    ]


def test_the_report_names_a_notable_moment_of_each_kind():
    """The format asks for two or three notable moments. There were none at all."""
    from zeg.report import assemble_report

    rendered = assemble_report(_mixed_call(), consent=True, interview_started_s=0).render()
    assert "Notable moments:" in rendered
    assert "Specific across" in rendered
    assert "stayed general" in rendered


def test_every_notable_moment_is_quoted_and_checkable():
    from zeg.report import assemble_report
    from zeg.scoring import notable_moments

    report = assemble_report(_mixed_call(), consent=True, interview_started_s=0)
    moments = notable_moments(report.moments_from)
    assert moments
    for moment in moments:
        assert moment.quote in report.render_transcript()


def test_a_call_with_nothing_notable_says_nothing():
    from zeg.conversation import TranscriptEntry as T
    from zeg.report import assemble_report

    plain = [T(0, "agent", "Tell me about it."), T(30, "caller", "I wrote the lock fix")]
    assert "Notable moments:" not in assemble_report(
        plain, consent=True, interview_started_s=0).render()
