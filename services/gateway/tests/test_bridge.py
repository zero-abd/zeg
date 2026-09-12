"""CallBridge drives a VoiceSession and gets barge-in right.

Runs against the mock backend, so no GPU and no WebRTC. Feeding a caller frame
is the clock, exactly as in the real transport: silence advances the agent's
reply; a loud frame while it is still speaking is a barge-in.
"""

from zeg.audio import AudioFrame, tone
from zeg.backends import MockBackend
from zeg.config import AudioConfig

from gateway.bridge import CallBridge


def _silence(cfg: AudioConfig) -> AudioFrame:
    return AudioFrame.silence(cfg.input_sample_rate, cfg.input_frame_samples, 0.0)


def _loud(cfg: AudioConfig) -> AudioFrame:
    f = tone(cfg.input_sample_rate, cfg.input_frame_samples, freq_hz=180.0, amplitude=0.3)
    return AudioFrame(f.pcm, f.sample_rate, 0.0)


def _make_bridge(greeting: str):
    cfg = AudioConfig()
    session = MockBackend(audio=cfg).start_session("system prompt", greeting=greeting)
    collected = []
    flushes = {"n": 0}
    bridge = CallBridge(
        session,
        on_agent_audio=lambda frame: collected.append(frame),
        on_interrupt=lambda: flushes.__setitem__("n", flushes["n"] + 1),
    )
    return cfg, bridge, collected, flushes


def test_greeting_audio_flows_out():
    cfg, bridge, collected, _ = _make_bridge("hello there, welcome to the call")
    for _ in range(15):
        bridge.feed(_silence(cfg))
    assert collected, "greeting should have produced agent audio frames"
    assert all(f.sample_rate == cfg.output_sample_rate for f in collected)
    assert any(speaker == "agent" for speaker, _ in bridge.transcript)
    assert bridge.agent_audio_s > 0.0


def test_barge_in_flushes_playback():
    cfg, bridge, collected, flushes = _make_bridge("this is a fairly long greeting so the agent keeps talking for a while")
    for _ in range(15):
        bridge.feed(_silence(cfg))
    assert collected  # agent is mid-greeting

    bridge.feed(_loud(cfg))  # candidate cuts in
    assert bridge.interruptions >= 1
    assert flushes["n"] >= 1, "barge-in must trigger a playback flush"


def test_no_spurious_interrupt_on_silence():
    cfg, bridge, _, flushes = _make_bridge("hi")
    for _ in range(30):
        bridge.feed(_silence(cfg))
    assert flushes["n"] == 0
    assert bridge.error is None
