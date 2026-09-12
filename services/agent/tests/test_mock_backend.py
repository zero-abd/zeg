import pytest

from zeg.audio import AudioFrame, tone
from zeg.backends import (
    AgentAudio,
    AgentInterrupted,
    AgentText,
    MockBackend,
    UserTranscript,
    build_backend,
)
from zeg.config import AudioConfig, BackendConfig


@pytest.fixture
def audio():
    return AudioConfig()


def drive(session, audio, n_frames, speaking=False):
    out = []
    for _ in range(n_frames):
        f = (
            tone(audio.input_sample_rate, audio.input_frame_samples, amplitude=0.3)
            if speaking
            else AudioFrame.silence(audio.input_sample_rate, audio.input_frame_samples)
        )
        session.push_audio(f)
        out.extend(session.poll())
    return out


def test_build_backend_defaults_to_mock():
    assert isinstance(build_backend(), MockBackend)


def test_unknown_backend_kind_is_rejected():
    with pytest.raises(ValueError):
        build_backend(BackendConfig(kind="nope"))


def test_greeting_is_spoken_before_any_caller_audio(audio):
    s = MockBackend(audio).start_session("sys", greeting="hello there friend")
    events = drive(s, audio, 20)
    assert any(isinstance(e, AgentText) and e.final for e in events)
    assert any(isinstance(e, AgentAudio) for e in events)


def test_agent_audio_is_at_the_model_output_rate(audio):
    s = MockBackend(audio).start_session("sys", greeting="hello there friend")
    events = drive(s, audio, 20)
    frames = [e.frame for e in events if isinstance(e, AgentAudio)]
    assert frames
    assert all(f.sample_rate == audio.output_sample_rate for f in frames)


def test_caller_speech_produces_partial_then_final_transcript(audio):
    s = MockBackend(audio).start_session("sys")
    events = drive(s, audio, 60, speaking=True)
    events += drive(s, audio, 20)
    tr = [e for e in events if isinstance(e, UserTranscript)]
    assert any(not e.final for e in tr), "expected partial hypotheses"
    assert any(e.final for e in tr), "expected a final transcript after the pause"


def test_endpoint_fires_after_about_200ms_of_silence(audio):
    s = MockBackend(audio).start_session("sys")
    drive(s, audio, 60, speaking=True)
    # 200 ms at 20 ms frames is 10 frames. Nine must not be enough.
    early = drive(s, audio, 9)
    assert not [e for e in early if isinstance(e, UserTranscript) and e.final]
    late = drive(s, audio, 3)
    assert [e for e in late if isinstance(e, UserTranscript) and e.final]


def test_caller_talking_over_the_agent_interrupts_it(audio):
    s = MockBackend(audio).start_session(
        "sys", greeting="this is a fairly long greeting that takes a while to say"
    )
    drive(s, audio, 8)  # let the agent get going
    events = drive(s, audio, 20, speaking=True)
    assert any(isinstance(e, AgentInterrupted) for e in events)


def test_interrupted_agent_stops_producing_audio(audio):
    s = MockBackend(audio).start_session(
        "sys", greeting="this is a fairly long greeting that takes a while to say"
    )
    drive(s, audio, 8)
    events = drive(s, audio, 20, speaking=True)
    idx = next(i for i, e in enumerate(events) if isinstance(e, AgentInterrupted))
    assert not [e for e in events[idx:] if isinstance(e, AgentAudio)]


def test_closed_session_rejects_audio(audio):
    s = MockBackend(audio).start_session("sys")
    s.close()
    with pytest.raises(RuntimeError):
        s.push_audio(AudioFrame.silence(audio.input_sample_rate, 320))


def test_close_is_idempotent(audio):
    s = MockBackend(audio).start_session("sys")
    s.close()
    s.close()
