"""Server-side lifecycle.

No model, no socket, no clock. Everything that actually breaks in a realtime voice
server is a lifecycle bug — a response that never terminates, two turns open at
once, a cancel that arrives after the thing it cancels — and none of those need a
GPU to reproduce.
"""

from zeg.runtime import protocol as p
from zeg.runtime.session import SETTLE_FRAMES_MAX, FrameResult, ResponseWatchdog, ServerSession

SILENCE = b"\x00" * p.OUTPUT_FRAME_BYTES


def types(messages):
    return [m["type"] for m in messages]


def configured_session(**kwargs):
    session = ServerSession("s1", **kwargs)
    session.on_client(p.Wire().configure("be brief", greeting="hello"))
    session.drain_actions()
    return session


def speak(session, frames, text="", audible=True):
    out = []
    for _ in range(frames):
        frame = FrameResult(text_delta=text, audio_pcm=SILENCE, audible=audible)
        out.extend(session.on_frame(frame))
    return out


# --- handshake ---------------------------------------------------------------


def test_configure_returns_the_ready_barrier():
    session = ServerSession("s1")
    out = session.on_client(p.Wire().configure("be brief"))
    assert types(out) == [p.CONFIGURED]
    assert session.instructions == "be brief"


def test_a_version_mismatch_is_fatal():
    session = ServerSession("s1")
    msg = p.Wire().configure("x")
    msg["session"]["protocol_version"] = 99
    out = session.on_client(msg)
    assert types(out) == [p.ERROR, p.CLOSED]
    assert out[0]["error"]["fatal"] is True
    assert session.closed


def test_audio_before_configure_is_fatal():
    session = ServerSession("s1")
    out = session.on_client(p.Wire().audio(b"\x00" * p.INPUT_FRAME_BYTES))
    assert p.ERROR in types(out)
    assert session.closed


def test_settings_lock_once_the_session_is_live():
    session = configured_session()
    out = session.on_client(p.Wire().configure("different prompt"))
    assert types(out) == [p.ERROR]
    assert out[0]["error"]["fatal"] is False
    assert session.instructions == "be brief"


def test_a_client_may_ask_for_a_shorter_session_but_not_a_longer_one():
    session = ServerSession("s1", max_session_frames=1000)
    session.on_client(p.Wire().configure("x", max_session_frames=100))
    assert session.max_session_frames == 100

    other = ServerSession("s2", max_session_frames=1000)
    other.on_client(p.Wire().configure("x", max_session_frames=99999))
    assert other.max_session_frames == 1000


# --- turns -------------------------------------------------------------------


def test_a_turn_is_acknowledged_and_correlated():
    session = configured_session()
    out = session.on_client(p.Wire().turn_start(1))
    assert types(out) == [p.TURN_STARTED]
    assert out[0]["turn"] == 1
    turn_id = out[0]["turn_id"]

    out = session.on_client(p.Wire().turn_commit(1))
    # The final transcript no longer rides on the commit. It waits for the recogniser
    # to settle and follows when the model opens its reply.
    assert types(out) == [p.TURN_COMMITTED]
    assert out[0]["turn_id"] == turn_id
    out = session.on_frame(FrameResult(control="response_open"))
    assert types(out) == [p.TRANSCRIPT_FINAL, p.RESPONSE_STARTED]
    assert out[0]["turn_id"] == turn_id


def test_a_repeated_turn_start_is_idempotent():
    session = configured_session()
    session.on_client(p.Wire().turn_start(1))
    out = session.on_client(p.Wire().turn_start(1))
    assert types(out) == [p.TURN_STARTED]
    assert not session.closed


def test_an_overlapping_turn_is_fatal():
    # A half-sent audio turn cannot be rolled back: the model has already consumed
    # those frames into its recurrent state.
    session = configured_session()
    session.on_client(p.Wire().turn_start(1))
    out = session.on_client(p.Wire().turn_start(2))
    assert out[0]["error"]["code"] == "overlapping_turn"
    assert session.closed


def test_a_commit_for_the_wrong_turn_is_fatal():
    session = configured_session()
    session.on_client(p.Wire().turn_start(1))
    out = session.on_client(p.Wire().turn_commit(2))
    assert out[0]["error"]["code"] == "turn_mismatch"
    assert session.closed


def test_a_commit_asks_the_loop_for_exactly_one_transition():
    session = configured_session()
    session.on_client(p.Wire().turn_start(1))
    session.drain_actions()
    session.on_client(p.Wire().turn_commit(1))
    kinds = [a.kind for a in session.drain_actions()]
    assert kinds == ["commit"]


def test_audio_flows_whether_or_not_a_turn_is_open():
    # The model is duplex: it hears the caller on every frame, which is the only
    # reason barge-in is possible at all.
    session = configured_session()
    session.on_client(p.Wire().audio(b"\x00" * p.INPUT_FRAME_BYTES))
    assert [a.kind for a in session.drain_actions()] == ["audio"]


def test_a_corrupt_audio_frame_is_recoverable_not_fatal():
    session = configured_session()
    bad = dict(p.Wire().audio(b"\x00" * p.INPUT_FRAME_BYTES), sample_rate=8000)
    out = session.on_client(bad)
    assert types(out) == [p.ERROR]
    assert out[0]["error"]["fatal"] is False
    assert not session.closed


# --- responses ---------------------------------------------------------------


def test_a_response_opens_speaks_and_terminates_once():
    session = configured_session()
    session.on_client(p.Wire().turn_start(1))
    session.on_client(p.Wire().turn_commit(1))

    # The committed turn's final transcript is held until the model settles, and goes
    # out just ahead of the reply that follows it.
    out = session.on_frame(FrameResult(control="response_open"))
    assert types(out) == [p.TRANSCRIPT_FINAL, p.RESPONSE_STARTED]

    out = session.on_frame(FrameResult(text_delta="hi", audio_pcm=SILENCE, audible=True))
    assert types(out) == [p.RESPONSE_TEXT, p.RESPONSE_AUDIO]

    out = session.on_frame(FrameResult(control="response_close"))
    assert types(out) == [p.RESPONSE_DONE]
    assert out[0]["status"] == "completed"

    # And nothing after it.
    assert session.on_frame(FrameResult(audio_pcm=SILENCE)) == []


def test_a_new_turn_terminates_an_open_response():
    session = configured_session()
    session.on_frame(FrameResult(control="response_open"))
    out = session.on_client(p.Wire().turn_start(1))
    assert types(out) == [p.RESPONSE_CANCELLED, p.RESPONSE_DONE, p.TURN_STARTED]
    assert out[1]["status"] == "cancelled"


def test_cancel_terminates_the_response_and_tells_the_loop():
    session = configured_session()
    session.on_frame(FrameResult(control="response_open"))
    session.drain_actions()
    out = session.on_client(p.Wire().cancel("barge_in"))
    assert types(out) == [p.RESPONSE_CANCELLED, p.RESPONSE_DONE]
    assert [a.kind for a in session.drain_actions()] == ["cancel"]


def test_cancelling_nothing_is_harmless():
    session = configured_session()
    assert session.on_client(p.Wire().cancel("barge_in")) == []


def test_transcripts_are_deltas_within_the_open_turn():
    session = configured_session()
    session.on_client(p.Wire().turn_start(1))
    out = session.on_frame(FrameResult(user_text="a race"))
    assert out[0]["delta"] == "a race"
    out = session.on_frame(FrameResult(user_text="a race condition"))
    assert out[0]["delta"] == " condition"
    assert out[0]["text"] == "a race condition"

    assert p.TRANSCRIPT_FINAL not in types(session.on_client(p.Wire().turn_commit(1)))
    final = session.on_frame(FrameResult(control="response_open"))
    assert final[0]["type"] == p.TRANSCRIPT_FINAL
    assert final[0]["text"] == "a race condition"


def test_recognizer_output_outside_a_turn_is_not_recorded():
    # Real, but unattributed. A floating fragment in a transcript that a human
    # will read as evidence is worse than a missing one.
    session = configured_session()
    assert session.on_frame(FrameResult(user_text="mumble")) == []


# --- watchdogs ---------------------------------------------------------------


def test_the_watchdog_closes_a_response_that_never_starts():
    # The opening frame counts: it is a real frame that produced nothing.
    watchdog = ResponseWatchdog(no_progress_frames=3, trailing_silence_frames=99)
    assert watchdog.observe(FrameResult(control="response_open")) is None
    assert watchdog.observe(FrameResult()) is None
    assert watchdog.observe(FrameResult()) == "no_progress"


def test_the_watchdog_closes_a_response_that_went_quiet_after_speaking():
    watchdog = ResponseWatchdog(no_progress_frames=99, trailing_silence_frames=2)
    watchdog.observe(FrameResult(control="response_open"))
    watchdog.observe(FrameResult(audible=True))
    assert watchdog.observe(FrameResult()) is None
    assert watchdog.observe(FrameResult()) == "trailing_silence"


def test_the_watchdog_fires_once():
    watchdog = ResponseWatchdog(no_progress_frames=2)
    watchdog.observe(FrameResult(control="response_open"))
    assert watchdog.observe(FrameResult()) == "no_progress"
    assert watchdog.observe(FrameResult()) is None


def test_the_watchdog_stays_quiet_while_the_agent_is_talking():
    watchdog = ResponseWatchdog(no_progress_frames=3, trailing_silence_frames=3)
    watchdog.observe(FrameResult(control="response_open"))
    for _ in range(20):
        assert watchdog.observe(FrameResult(audible=True)) is None


def test_a_stalled_response_is_closed_as_failed_and_the_loop_is_told():
    session = configured_session(watchdog=ResponseWatchdog(no_progress_frames=2))
    session.on_frame(FrameResult(control="response_open"))
    session.drain_actions()
    out = session.on_frame(FrameResult())
    assert types(out) == [p.RESPONSE_DONE]
    assert out[0]["status"] == "failed"
    assert out[0]["reason"] == "no_progress"
    assert [a.kind for a in session.drain_actions()] == ["cancel"]


def test_a_response_that_went_quiet_after_speaking_is_closed_as_completed():
    """It was heard. Closing it as failed told the client it was never spoken, so the
    agent's whole line was missing from the transcript."""
    session = configured_session(
        watchdog=ResponseWatchdog(no_progress_frames=99, trailing_silence_frames=2)
    )
    session.on_frame(FrameResult(control="response_open", text_delta="What broke?",
                                 audio_pcm=SILENCE, audible=True))
    session.drain_actions()
    out = session.on_frame(FrameResult(audio_pcm=SILENCE))
    out += session.on_frame(FrameResult(audio_pcm=SILENCE))
    done = [m for m in out if m["type"] == p.RESPONSE_DONE]
    assert len(done) == 1
    assert done[0]["status"] == "completed"
    assert done[0]["reason"] == "trailing_silence"
    assert [a.kind for a in session.drain_actions()] == ["cancel"]


def test_the_runtime_never_invents_something_to_say():
    # A stalled response produces a terminal, never text.
    session = configured_session(watchdog=ResponseWatchdog(no_progress_frames=1))
    out = session.on_frame(FrameResult(control="response_open"))
    assert not [m for m in out if m["type"] == p.RESPONSE_TEXT]
    assert out[-1]["type"] == p.RESPONSE_DONE


# --- budget and closing ------------------------------------------------------


def test_progress_is_reported_periodically():
    session = configured_session()
    out = speak(session, 25)
    progress = [m for m in out if m["type"] == p.PROGRESS]
    assert len(progress) == 1
    assert progress[0]["frames"] == 25
    assert progress[0]["remaining"] == p.MAX_SESSION_FRAMES - 25


def test_over_budget_frames_are_counted_not_hidden():
    session = configured_session()
    session.on_frame(FrameResult(over_budget=True))
    session.on_frame(FrameResult())
    assert session.over_budget == 1


def test_the_session_closes_at_the_frame_cap():
    session = configured_session(max_session_frames=4)
    out = speak(session, 4)
    assert p.CLOSED in types(out)
    assert out[-1]["reason"] == "session_frame_cap"
    assert session.closed


def test_a_closed_session_ignores_everything_after():
    session = configured_session(max_session_frames=1)
    session.on_frame(FrameResult())
    assert session.on_client(p.Wire().turn_start(1)) == []
    assert session.on_frame(FrameResult()) == []


def test_stop_closes_every_open_bracket():
    session = configured_session()
    session.on_client(p.Wire().turn_start(1))
    session.on_frame(FrameResult(control="response_open"))
    out = session.on_client(p.Wire().stop())
    assert types(out) == [p.TRANSCRIPT_FINAL, p.RESPONSE_DONE, p.CLOSED]


def test_close_is_idempotent():
    session = configured_session()
    assert session.close("done")
    assert session.close("done") == []


# --- words the recogniser confirms while it settles --------------------------------


def committed(session, heard=""):
    """Open turn 1, let it hear `heard`, commit it. Returns the turn id."""
    turn_id = session.on_client(p.Wire().turn_start(1))[0]["turn_id"]
    if heard:
        session.on_frame(FrameResult(user_text=heard))
    session.on_client(p.Wire().turn_commit(1))
    return turn_id


def test_words_confirmed_while_the_recogniser_settles_reach_the_final_transcript():
    """The final transcript went out at the commit, before the model settled, and words
    the recogniser confirmed while settling arrived with no turn open and were dropped."""
    session = configured_session()
    turn_id = committed(session, heard="yes that is")
    out = session.on_frame(FrameResult(user_text="yes that is fine"))
    assert types(out) == [p.TRANSCRIPT_DELTA]
    assert out[0]["delta"] == " fine"
    assert out[0]["turn_id"] == turn_id
    out = session.on_frame(FrameResult(control="response_open"))
    assert types(out) == [p.TRANSCRIPT_FINAL, p.RESPONSE_STARTED]
    assert out[0]["text"] == "yes that is fine"


def test_a_one_word_answer_confirmed_only_while_settling_is_not_lost():
    """A candidate who answered "yes" produced an empty final, which the client drops."""
    session = configured_session()
    committed(session)
    out = session.on_frame(FrameResult(user_text="yes", control="response_open"))
    assert [m["text"] for m in out if m["type"] == p.TRANSCRIPT_FINAL] == ["yes"]
    assert types(out).index(p.TRANSCRIPT_FINAL) < types(out).index(p.RESPONSE_STARTED)


def test_a_model_that_never_replies_still_gets_its_turn_finalised():
    session = configured_session()
    committed(session, heard="a race condition")
    out = []
    for _ in range(SETTLE_FRAMES_MAX):
        out.extend(session.on_frame(FrameResult()))
    assert [m["text"] for m in out if m["type"] == p.TRANSCRIPT_FINAL] == ["a race condition"]


def test_the_final_transcript_is_sent_exactly_once():
    session = configured_session()
    committed(session, heard="yes")
    out = session.on_frame(FrameResult(control="response_open"))
    for _ in range(SETTLE_FRAMES_MAX * 2):
        out.extend(session.on_frame(FrameResult(audio_pcm=SILENCE, audible=True)))
    assert types(out).count(p.TRANSCRIPT_FINAL) == 1


def test_a_new_turn_while_settling_finalises_the_previous_turn_first():
    session = configured_session()
    first = committed(session, heard="yes")
    out = session.on_client(p.Wire().turn_start(2))
    assert types(out) == [p.TRANSCRIPT_FINAL, p.TURN_STARTED]
    assert out[0]["turn_id"] == first
    assert out[0]["text"] == "yes"


def test_closing_while_settling_finalises_the_turn():
    session = configured_session()
    committed(session, heard="no thanks")
    out = session.on_client(p.Wire().stop())
    assert types(out) == [p.TRANSCRIPT_FINAL, p.CLOSED]
    assert out[0]["text"] == "no thanks"


def test_recognizer_output_after_the_final_is_still_not_recorded():
    session = configured_session()
    committed(session, heard="yes")
    session.on_frame(FrameResult(control="response_open"))
    assert p.TRANSCRIPT_DELTA not in types(session.on_frame(FrameResult(user_text="yes and more")))
