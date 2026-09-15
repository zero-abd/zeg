"""The whole interview, through the real client, the real server and the real wire.

Every layer had been tested against a fake of the layer beside it. This runs the
interview engine against the real backend, where every connection is a real server
session over the in-memory loopback and the model stand-in steps on the real frame
loop.

The stand-in cannot hear and cannot think. The harness supplies every turn boundary,
and every reply is the stand-in's one fixed line, whatever the engine steered it
towards. What is under test is that the layers agree with each other, not that the
interview is any good.
"""

from fakes import LoopbackLink
from zeg.backends.gb10 import GB10Backend
from zeg.config import BackendConfig
from zeg.conversation import InterviewRunner
from zeg.runtime import protocol as p
from zeg.runtime.model import SilenceModel
from zeg.scoring import score_call

REPLY = "Tell me more about that."


def run_stack(caller=None, runtime=None):
    links = []

    def factory():
        link = LoopbackLink(SilenceModel(reply_frames=12, reply_text=REPLY))
        links.append(link)
        return link

    backend = GB10Backend(BackendConfig(kind="gb10"), runtime=runtime, link_factory=factory)
    runner = InterviewRunner(backend)
    result = runner.run(caller) if caller else runner.run()
    return result, links


def test_the_whole_interview_runs_through_the_real_stack_without_a_server_error():
    result, links = run_stack()
    assert links, "no connection was ever opened"
    for link in links:
        assert not link.errors(), link.errors()


def test_consent_is_taken_over_the_real_wire():
    result, _ = run_stack()
    assert result.consent is True
    assert "AI interviewer" in result.transcript[0].text


def test_the_disclosure_is_voiced_by_the_server_not_only_recorded():
    """The fixed line travels client, server, frame loop, model and back as audio."""
    result, links = run_stack()
    assert result.agent_audio_frames > 0
    assert p.RESPONSE_STARTED in links[0].received_types()


def test_the_engine_steers_the_model_over_the_real_wire():
    result, links = run_stack()
    assert result.probes, "no probe was issued"
    assert links[0].model.context, "no steer ever reached the model"


def test_the_stand_in_cannot_hear_so_the_harness_supplies_every_turn():
    result, _ = run_stack()
    callers = [t for t in result.transcript if t.speaker == "caller"]
    assert callers
    assert result.synthesised_turns == len(callers)


def test_the_real_stack_produces_a_scoreable_transcript():
    result, _ = run_stack()
    assert score_call(result.transcript).overall is not None


# --- when the backend fails mid-call ----------------------------------------------


def test_a_backend_failure_mid_call_ends_it_instead_of_crashing_it():
    """The runtime closed the session at its frame cap. The client queued a fatal
    error, the runner never read it, pushed the next frame into the closed session and
    raised. On the box that is an interview with no transcript and no report."""
    from zeg.backends.gb10 import GB10Config

    result, _ = run_stack(runtime=GB10Config(max_session_frames=30))
    assert result.failed
    assert result.ended.startswith("backend failed")
    assert result.errors
    assert result.transcript, "what was said before the failure still comes back"


# --- a candidate who declines has to hear why the call is ending --------------------


def voiced(link, line):
    """Whether the server actually spoke this line.

    Counting replies was not enough. The stand-in answers every committed turn on its
    own, so a second reply could be its canned line while the decline was never spoken,
    and a test counting replies passed on the code that never voiced it.
    """
    return any(line in (m.get("text") or "") for m in link.received if m["type"] == p.RESPONSE_TEXT)


def test_a_candidate_who_declines_with_a_short_pause_hears_the_decline_line():
    """Two things lost this line. The server refused it because the candidate's turn
    was still open, and the runner closed the session the instant the call ended, so
    even a line that was accepted never played. The client now holds the line until
    the turn commits, and the runner lets it play before closing."""
    from zeg.conversation import CallerTurn

    result, links = run_stack([CallerTurn("no, I'd rather not", speak_s=1.5, pause_after_s=0.3)])
    assert result.consent is False
    from zeg.prompts import CONSENT_DECLINED

    assert len([m for m in links[0].sent if m["type"] == p.SAY]) == 2, "greeting and decline"
    assert voiced(links[0], CONSENT_DECLINED), "the decline was never voiced"
    assert not links[0].errors()


def test_the_decline_line_plays_after_an_ordinary_pause_too():
    from zeg.conversation import CallerTurn

    from zeg.prompts import CONSENT_DECLINED

    result, links = run_stack([CallerTurn("no thank you", speak_s=1.5)])
    assert result.consent is False
    assert voiced(links[0], CONSENT_DECLINED), "the decline was never voiced"
    assert not links[0].errors()


# --- rollover over the real wire --------------------------------------------------


def unanswered_probe(link):
    """The last probe this session was told to ask, if the candidate never got to answer
    it before the session closed. An answer shows up as a committed turn after it."""
    pending = None
    for m in link.sent:
        if m["type"] == p.STEER and m["text"].startswith("Ask for"):
            pending = m["text"]
        elif m["type"] == p.TURN_COMMIT:
            pending = None
    return pending


def test_rollover_never_closes_a_session_on_a_question_it_did_not_get_to_ask():
    """The rollover policy waits for the probe ladder to finish, and it counted the
    ladder finished when its last question was issued rather than answered. So it
    rolled on that turn, and on every rollover the final question, what broke
    afterwards, went into a model that closed a moment later."""
    from zeg.conversation import CallerTurn
    from zeg.interview import Interview
    from zeg.memory import RolloverPolicy

    links = []

    def factory():
        link = LoopbackLink(SilenceModel(reply_frames=12, reply_text=REPLY))
        links.append(link)
        return link

    caller = [CallerTurn("yes that is fine", speak_s=1.5)] + [
        CallerTurn("we cut reconciler p99 latency from 400ms to 30ms", speak_s=4.0)
    ] * 12
    interview = Interview(rollover=RolloverPolicy(context_horizon_s=20, min_session_s=10))
    backend = GB10Backend(BackendConfig(kind="gb10"), link_factory=factory)
    result = InterviewRunner(backend, interview=interview).run(caller)

    assert result.rollovers >= 1, "the call never rolled, so this proves nothing"
    for i, link in enumerate(links[:-1]):
        assert unanswered_probe(link) is None, (
            "connection %d closed before its candidate answered: %r"
            % (i, unanswered_probe(link))
        )
    for link in links:
        assert not link.errors()


# --- talking over the disclosure, over the real wire --------------------------------


def test_a_candidate_who_talks_over_the_disclosure_hears_it_again_before_consenting():
    """The server cut the disclosure off, the interview took the words spoken over it as
    consent, and the transcript still showed the disclosure in full."""
    from zeg.conversation import CallerTurn

    caller = [
        CallerTurn("yeah go ahead", speak_s=1.5, barge_in=True),
        CallerTurn("yes that is fine", speak_s=1.5),
        CallerTurn("a race condition in our payment reconciler", speak_s=3.0),
    ]
    result, links = run_stack(caller)
    disclosures = [m for m in links[0].sent if m["type"] == p.SAY and "AI interviewer" in m["text"]]

    assert result.interruptions >= 1, "the candidate never actually cut in"
    assert len(disclosures) == 2, "the disclosure was not repeated after being cut off"
    assert result.consent is True
    assert any("talked over the recording disclosure" in f for f in result.flags)
    assert not links[0].errors()


# --- only what was actually said reaches the transcript ------------------------------


def completed_reply_count(link, text):
    """How many of the server's responses finished speaking exactly this text."""
    spoken = {}
    for m in link.received:
        if m["type"] == p.RESPONSE_TEXT:
            spoken[m.get("response_id")] = m.get("text") or ""
    return sum(
        1 for m in link.received
        if m["type"] == p.RESPONSE_DONE and m.get("status") == "completed"
        and spoken.get(m.get("response_id")) == text
    )


def agent_lines(result, text):
    return len([t for t in result.transcript if t.speaker == "agent" and t.text == text])


def test_a_reply_stopped_for_the_disclosure_is_not_recorded_as_said():
    """The client stopped the model's own reply to repeat the disclosure, and the stopped
    reply still landed in the transcript as a line the agent had said. Sitting between the
    repeated disclosure and its echo, it also got the disclosure recorded a third time."""
    from zeg.conversation import CallerTurn

    caller = [
        CallerTurn("yeah go ahead", speak_s=1.5, barge_in=True),
        CallerTurn("yes that is fine", speak_s=1.5),
        CallerTurn("a race condition in our payment reconciler", speak_s=3.0),
    ]
    result, links = run_stack(caller)
    done = [m for m in links[0].received if m["type"] == p.RESPONSE_DONE]
    assert any(m.get("status") == "cancelled" for m in done), "nothing was stopped, so this proves nothing"

    assert agent_lines(result, REPLY) == completed_reply_count(links[0], REPLY)
    disclosures = [t for t in result.transcript if t.speaker == "agent" and "AI interviewer" in t.text]
    assert len(disclosures) == 2, "the disclosure was recorded %d times" % len(disclosures)


def test_a_reply_the_candidate_talked_over_is_not_recorded_as_said():
    from zeg.conversation import CallerTurn

    links = []

    def factory():
        link = LoopbackLink(SilenceModel(reply_frames=200, reply_text=REPLY))
        links.append(link)
        return link

    caller = [
        CallerTurn("yes that is fine", speak_s=1.5),
        CallerTurn("a race condition in our payment reconciler", speak_s=2.0),
        CallerTurn("actually wait, let me add something", speak_s=2.0, barge_in=True),
    ]
    result = InterviewRunner(GB10Backend(BackendConfig(kind="gb10"), link_factory=factory)).run(caller)
    assert result.interruptions >= 1, "the candidate never cut in, so this proves nothing"
    assert agent_lines(result, REPLY) == completed_reply_count(links[0], REPLY)
    assert not links[0].errors()
