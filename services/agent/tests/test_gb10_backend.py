"""The GB10 backend, driven against a fake connection.

Everything that can be tested without a GPU is tested here: the handshake, turn
barriers, frame aggregation, transcripts, barge-in, the watchdog and the session
frame cap. The model is absent and so is the socket; what is under test is the
half of the system that decides when the model is allowed to speak.

The behaviour asserted here is deliberately the same behaviour `test_mock_backend`
asserts of the mock. Two implementations of one contract are only useful if they
are actually interchangeable.
"""

import collections

import pytest

from zeg.audio import AudioFrame, tone
from zeg.backends import AgentAudio, AgentInterrupted, AgentText, BackendError, UserTranscript
from zeg.backends.gb10 import GB10Backend, GB10Config, GB10Session
from zeg.config import AudioConfig, BackendConfig
from zeg.runtime import protocol as p

from fakes import FakeLink, agent_frame




@pytest.fixture
def audio():
    return AudioConfig()


def session(link, audio, **kwargs):
    return GB10Session(link, "be brief", audio=audio, config=GB10Config(**kwargs))


def drive(sess, audio, n, speaking=False):
    """Push n transport frames and collect whatever comes back.

    Stops early once the session has ended itself, which is what the layer above
    does: a fatal error is the end of the call, not something to push through.
    """
    out = []
    for _ in range(n):
        if sess.closed:
            return out
        frame = (
            tone(audio.input_sample_rate, audio.input_frame_samples, amplitude=0.3)
            if speaking
            else AudioFrame.silence(audio.input_sample_rate, audio.input_frame_samples)
        )
        sess.push_audio(frame)
        out.extend(sess.poll())
    return out




# --- handshake ---------------------------------------------------------------


def test_the_session_configures_itself_before_anything_else(audio):
    link = FakeLink()
    session(link, audio)
    assert link.types()[0] == p.CONFIGURE
    assert link.sent[0]["session"]["instructions"] == "be brief"


def test_the_greeting_is_handed_to_the_runtime_not_left_to_the_model(audio):
    link = FakeLink()
    GB10Session(link, "sys", greeting="hello, I am an AI interviewer", audio=audio)
    assert link.sent[0]["session"]["greeting"] == "hello, I am an AI interviewer"


def test_audio_before_the_runtime_is_ready_is_discarded_not_buffered(audio):
    # Replaying stale audio into a model that is now listening answers a question
    # the candidate has already moved on from.
    link = FakeLink(auto_ready=False)
    sess = session(link, audio)
    drive(sess, audio, 20, speaking=True)
    assert sess.discarded_frames == 20
    assert link.of_type(p.AUDIO) == []


def test_a_protocol_version_mismatch_is_fatal(audio):
    link = FakeLink(auto_ready=False)
    sess = session(link, audio)
    link.deliver({"type": p.READY, "protocol": {"name": p.PROTOCOL_NAME, "version": 99}})
    events = list(sess.poll())
    assert any(isinstance(e, BackendError) and e.fatal for e in events)


# --- frames and turns --------------------------------------------------------


def test_four_transport_frames_make_one_model_frame(audio):
    link = FakeLink()
    sess = session(link, audio)
    drive(sess, audio, 8)
    assert len(link.of_type(p.AUDIO)) == 2
    assert sess.model_frames == 2


def test_every_model_frame_is_exactly_eighty_milliseconds(audio):
    link = FakeLink()
    sess = session(link, audio)
    drive(sess, audio, 12)
    for msg in link.of_type(p.AUDIO):
        assert len(p.decode_input_audio(msg)) == p.INPUT_FRAME_BYTES


def test_speech_opens_a_turn_and_a_pause_commits_it(audio):
    link = FakeLink()
    sess = session(link, audio, endpoint_silence_ms=200)
    drive(sess, audio, 20, speaking=True)
    assert link.of_type(p.TURN_START), "speech should open a turn"
    assert not link.of_type(p.TURN_COMMIT), "a turn must not commit while talking"

    drive(sess, audio, 10)  # 200 ms of silence
    commits = link.of_type(p.TURN_COMMIT)
    assert commits, "a pause should commit the turn"
    assert commits[0]["turn"] == link.of_type(p.TURN_START)[0]["turn"]


def test_a_short_pause_does_not_commit_a_turn(audio):
    # The endpoint is the difference between a natural pause and an interruption.
    link = FakeLink()
    sess = session(link, audio, endpoint_silence_ms=640)
    drive(sess, audio, 20, speaking=True)
    drive(sess, audio, 20)  # 400 ms, less than the endpoint
    assert not link.of_type(p.TURN_COMMIT)


def test_turns_are_numbered_in_order(audio):
    link = FakeLink()
    sess = session(link, audio, endpoint_silence_ms=200)
    for _ in range(3):
        drive(sess, audio, 10, speaking=True)
        drive(sess, audio, 12)
    assert [m["turn"] for m in link.of_type(p.TURN_START)] == [1, 2, 3]
    assert [m["turn"] for m in link.of_type(p.TURN_COMMIT)] == [1, 2, 3]


def test_a_turn_claims_the_frames_that_carried_its_onset(audio):
    # The gate always fires late. Without pre-roll the model loses the first
    # syllable and confabulates it back.
    link = FakeLink()
    sess = session(link, audio)
    drive(sess, audio, 8, speaking=True)
    assert link.of_type(p.TURN_START)[0]["preroll_frames"] >= 1


def test_a_commit_never_splits_a_model_frame(audio):
    link = FakeLink()
    sess = session(link, audio, endpoint_silence_ms=200)
    drive(sess, audio, 6, speaking=True)  # one and a half model frames
    drive(sess, audio, 10)
    order = [m["type"] for m in link.sent if m["type"] in (p.AUDIO, p.TURN_COMMIT)]
    # Everything buffered is flushed as a whole frame before the commit goes out.
    assert order[-1] == p.TURN_COMMIT
    for msg in link.of_type(p.AUDIO):
        assert len(p.decode_input_audio(msg)) == p.INPUT_FRAME_BYTES


def test_a_frame_at_the_wrong_rate_is_refused(audio):
    # Resampling belongs in the media path, with a real anti-alias filter.
    link = FakeLink()
    sess = session(link, audio)
    with pytest.raises(ValueError):
        sess.push_audio(AudioFrame.silence(8000, 160))


# --- what comes back ---------------------------------------------------------


def test_transcripts_arrive_partial_then_final(audio):
    link = FakeLink()
    sess = session(link, audio)
    link.deliver(link.wire.transcript_delta("t1", "a race", "a race"))
    link.deliver(link.wire.transcript_final("t1", "a race condition"))
    events = drive(sess, audio, 1)
    transcripts = [e for e in events if isinstance(e, UserTranscript)]
    assert [(t.text, t.final) for t in transcripts] == [
        ("a race", False),
        ("a race condition", True),
    ]


def test_agent_audio_is_at_the_model_output_rate(audio):
    link = FakeLink()
    sess = session(link, audio)
    link.deliver(link.wire.response_started("r1", "t1"))
    link.deliver(agent_frame(link))
    events = drive(sess, audio, 4)
    frames = [e.frame for e in events if isinstance(e, AgentAudio)]
    assert len(frames) == 4, "one 80 ms model frame is four 20 ms transport frames"
    assert all(f.sample_rate == audio.output_sample_rate for f in frames)
    assert all(f.n_samples == audio.output_frame_samples for f in frames)


def test_agent_audio_is_paced_against_the_caller_clock(audio):
    # Flushing a whole reply at once would leave nothing for barge-in to cancel.
    link = FakeLink()
    sess = session(link, audio)
    link.deliver(link.wire.response_started("r1", "t1"))
    link.deliver(agent_frame(link))
    events = drive(sess, audio, 1)
    assert len([e for e in events if isinstance(e, AgentAudio)]) == 1


def test_a_finished_response_yields_one_final_agent_text(audio):
    link = FakeLink()
    sess = session(link, audio)
    link.deliver(link.wire.response_started("r1", "t1"))
    link.deliver(link.wire.response_text("r1", "tell me ", "tell me "))
    link.deliver(link.wire.response_text("r1", "about the bug", "tell me about the bug"))
    link.deliver(link.wire.response_done("r1", "completed", "model_turn_end"))
    events = drive(sess, audio, 1)
    finals = [e for e in events if isinstance(e, AgentText) and e.final]
    assert [e.text for e in finals] == ["tell me about the bug"]


# --- barge-in ----------------------------------------------------------------


def test_the_caller_talking_over_the_agent_interrupts_it(audio):
    link = FakeLink()
    sess = session(link, audio)
    link.deliver(link.wire.response_started("r1", "t1"))
    for n in range(4):
        link.deliver(agent_frame(link, frame=n))
    drive(sess, audio, 2)  # agent gets going

    events = drive(sess, audio, 4, speaking=True)
    assert any(isinstance(e, AgentInterrupted) for e in events)


def test_barge_in_does_not_wait_for_the_runtime_to_agree(audio):
    # A round trip plus a model step is another 80 ms of the agent talking over a
    # candidate, so the interrupt is emitted locally and the cancel is sent after.
    link = FakeLink()
    sess = session(link, audio)
    link.deliver(link.wire.response_started("r1", "t1"))
    link.deliver(agent_frame(link))
    drive(sess, audio, 1)
    # Long enough to count as speech. One frame is a cough, and the gate is
    # deliberately unmoved by those; what is under test here is that once it is
    # convinced, it does not then wait for the runtime to agree.
    events = drive(sess, audio, GB10Config().min_speech_frames, speaking=True)
    assert any(isinstance(e, AgentInterrupted) for e in events)
    assert link.of_type(p.CANCEL), "the runtime still has to close its response"


def test_an_interrupted_agent_stops_producing_audio(audio):
    link = FakeLink()
    sess = session(link, audio)
    link.deliver(link.wire.response_started("r1", "t1"))
    for n in range(6):
        link.deliver(agent_frame(link, frame=n))
    drive(sess, audio, 2)
    events = drive(sess, audio, 10, speaking=True)
    idx = next(i for i, e in enumerate(events) if isinstance(e, AgentInterrupted))
    assert not [e for e in events[idx:] if isinstance(e, AgentAudio)]


def test_audio_for_a_cancelled_response_is_dropped(audio):
    # It is already in flight when the cancel is sent; playing it is the exact
    # thing the cancel existed to prevent.
    link = FakeLink()
    sess = session(link, audio)
    link.deliver(link.wire.response_started("r1", "t1"))
    link.deliver(agent_frame(link))
    drive(sess, audio, 1)
    drive(sess, audio, GB10Config().min_speech_frames, speaking=True)  # barge in
    link.deliver(agent_frame(link, frame=9))
    events = drive(sess, audio, 4)
    assert not [e for e in events if isinstance(e, AgentAudio)]


def test_the_runtime_cancelling_first_is_also_reported(audio):
    # Its own watchdog may close a response we never interrupted.
    link = FakeLink()
    sess = session(link, audio)
    link.deliver(link.wire.response_started("r1", "t1"))
    link.deliver(link.wire.response_cancelled("r1", "no_progress"))
    events = drive(sess, audio, 1)
    interrupts = [e for e in events if isinstance(e, AgentInterrupted)]
    assert len(interrupts) == 1
    assert interrupts[0].reason == "no_progress"


def test_one_interrupt_per_response_however_long_the_caller_talks(audio):
    link = FakeLink()
    sess = session(link, audio)
    link.deliver(link.wire.response_started("r1", "t1"))
    for n in range(8):
        link.deliver(agent_frame(link, frame=n))
    drive(sess, audio, 2)
    events = drive(sess, audio, 30, speaking=True)
    assert len([e for e in events if isinstance(e, AgentInterrupted)]) == 1


# --- failing safe ------------------------------------------------------------


def test_the_watchdog_ends_a_call_the_runtime_has_stopped_answering(audio):
    link = FakeLink()
    sess = session(link, audio, watchdog_frames=10)
    events = drive(sess, audio, 12)
    errors = [e for e in events if isinstance(e, BackendError)]
    assert errors and errors[0].fatal
    assert "silent" in errors[0].message
    assert sess.closed, "a wedged runtime ends the call rather than hanging"


def test_any_message_from_the_runtime_resets_the_watchdog(audio):
    link = FakeLink()
    sess = session(link, audio, watchdog_frames=10)
    for _ in range(4):
        drive(sess, audio, 8)
        link.deliver(link.wire.progress(1, 1, 0))
    assert not sess.closed


def test_the_watchdog_counts_caller_frames_not_wall_clock(audio):
    # Caller audio arrives in real time by definition, so counting it is counting
    # elapsed call time, and the failure path stays reproducible under the virtual
    # clock the conversation harness uses.
    link = FakeLink()
    sess = session(link, audio, watchdog_frames=5)
    drive(sess, audio, 4)
    assert not sess.closed
    drive(sess, audio, 1)
    assert sess.closed


def test_the_session_frame_cap_ends_the_call(audio):
    link = FakeLink()
    sess = session(link, audio, max_session_frames=3)
    events = drive(sess, audio, 20)
    errors = [e for e in events if isinstance(e, BackendError)]
    assert errors and errors[0].fatal
    assert "frame budget" in errors[0].message
    assert sess.model_frames <= 3


def test_the_runtimes_frame_count_wins(audio):
    # It steps the model; we only feed it. Taking the larger of the two keeps the
    # cap honest if a frame was ever dropped on the way in.
    link = FakeLink()
    sess = session(link, audio, max_session_frames=100)
    link.deliver(link.wire.progress(90, 10, 0))
    drive(sess, audio, 1)
    assert sess.model_frames == 90


def test_a_fatal_runtime_error_closes_the_session(audio):
    link = FakeLink()
    sess = session(link, audio)
    link.deliver(link.wire.error("model_error", "step failed", fatal=True))
    events = drive(sess, audio, 1)
    assert any(isinstance(e, BackendError) and e.fatal for e in events)
    assert sess.closed


def test_a_recoverable_runtime_error_does_not_end_the_call(audio):
    link = FakeLink()
    sess = session(link, audio)
    link.deliver(link.wire.error("bad_audio", "short frame", fatal=False))
    events = drive(sess, audio, 1)
    assert any(isinstance(e, BackendError) and not e.fatal for e in events)
    assert not sess.closed


def test_the_runtime_closing_unasked_is_an_error(audio):
    link = FakeLink()
    sess = session(link, audio)
    link.deliver(link.wire.closed("session_frame_cap"))
    events = drive(sess, audio, 1)
    assert any(isinstance(e, BackendError) and e.fatal for e in events)


def test_our_own_close_is_not_an_error(audio):
    link = FakeLink()
    sess = session(link, audio)
    sess.close()
    assert link.of_type(p.STOP), "the runtime is told, not just dropped"
    assert link.closed


# --- the contract everything else relies on ----------------------------------


def test_closed_session_rejects_audio(audio):
    link = FakeLink()
    sess = session(link, audio)
    sess.close()
    with pytest.raises(RuntimeError):
        sess.push_audio(AudioFrame.silence(audio.input_sample_rate, 320))


def test_close_is_idempotent(audio):
    link = FakeLink()
    sess = session(link, audio)
    sess.close()
    sess.close()


def test_the_backend_serves_one_conversation_at_a_time():
    # The model is batch-one and stateful. A second session would not be a second
    # conversation, it would be the same one with two people talking into it.
    backend = GB10Backend(BackendConfig(kind="gb10"), link_factory=FakeLink)
    backend.start_session("sys")
    with pytest.raises(RuntimeError):
        backend.start_session("sys")


def test_the_backend_reuses_the_slot_once_a_call_ends():
    backend = GB10Backend(BackendConfig(kind="gb10"), link_factory=FakeLink)
    first = backend.start_session("sys")
    first.close()
    second = backend.start_session("sys")
    assert second is not first


def test_warmup_checks_the_runtime_is_up_before_anyone_is_on_the_line():
    links = []

    def factory():
        link = FakeLink()
        link.deliver(link.wire.ready("s1", {}))
        links.append(link)
        return link

    GB10Backend(BackendConfig(kind="gb10"), link_factory=factory).warmup()
    assert links and links[0].closed


# --- rollover through the interview runner, on this backend --------------------


def test_the_runners_rollover_succeeds_on_the_real_backend():
    """The runner used to open the new session before closing the old one. This
    backend refuses a second live session, so the first rollover of every long call
    would have raised. Every rollover test ran against the mock, which does not."""
    from zeg.conversation import InterviewRunner
    from zeg.memory import SessionSeed

    backend = GB10Backend(BackendConfig(kind="gb10"), link_factory=FakeLink)
    runner = InterviewRunner(backend)
    first = backend.start_session("standing rules")
    runner._session = first

    runner._roll(SessionSeed("standing rules", "Phase: depth_two.", ["Candidate: a lock."]))

    assert first.closed
    assert runner._session is not first
    assert not runner._session.closed


def test_a_rolled_session_on_the_real_backend_is_steered_with_the_seed():
    from zeg.conversation import InterviewRunner
    from zeg.memory import SessionSeed

    backend = GB10Backend(BackendConfig(kind="gb10"), link_factory=FakeLink)
    runner = InterviewRunner(backend)
    runner._session = backend.start_session("standing rules")

    runner._roll(SessionSeed("standing rules", "Phase: depth_two.", ["Candidate: a lock."]))

    steers = runner._session._link.of_type(p.STEER)
    assert len(steers) == 1
    assert "Candidate: a lock." in steers[0]["text"]
    assert "standing rules" not in steers[0]["text"]


def test_opening_before_closing_is_exactly_what_this_backend_refuses():
    backend = GB10Backend(BackendConfig(kind="gb10"), link_factory=FakeLink)
    backend.start_session("sys")
    with pytest.raises(RuntimeError):
        backend.start_session("sys")


# --- say and steer on the real session -----------------------------------------


def test_steer_sends_one_context_message_on_the_real_session(audio):
    """Both methods named a module this file never imported, so every call raised.
    Only the mock and the server session had ever been tested, and neither is this."""
    link = FakeLink()
    sess = session(link, audio)
    sess.steer("Still no evidence for ownership.")
    assert [m["text"] for m in link.of_type(p.STEER)] == ["Still no evidence for ownership."]


def test_say_sends_one_fixed_utterance_on_the_real_session(audio):
    link = FakeLink()
    sess = session(link, audio)
    sess.say("This call is recorded. Is that okay?")
    assert [m["text"] for m in link.of_type(p.SAY)] == ["This call is recorded. Is that okay?"]


def test_neither_is_accepted_on_a_closed_real_session(audio):
    link = FakeLink()
    sess = session(link, audio)
    sess.close()
    with pytest.raises(RuntimeError):
        sess.steer("anything")
    with pytest.raises(RuntimeError):
        sess.say("anything")


def test_say_over_a_speaking_agent_cancels_it_first_on_the_real_session(audio):
    """The only path that reads the speaking check with the agent talking. It called a
    property as if it were a method, which raised on every say regardless."""
    link = FakeLink()
    sess = session(link, audio)
    link.deliver(link.wire.response_started("r1", "t1"))
    link.deliver(agent_frame(link))
    drive(sess, audio, 1)

    sess.say("That is my time. Thanks for talking me through it.")

    assert link.of_type(p.CANCEL), "a speaking agent has to be stopped before the fixed line"
    assert [m["text"] for m in link.of_type(p.SAY)] == [
        "That is my time. Thanks for talking me through it."
    ]
    assert any(isinstance(e, AgentInterrupted) for e in sess.poll())
