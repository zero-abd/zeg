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
