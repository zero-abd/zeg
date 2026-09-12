"""PlaybackBuffer serves fixed frames, pads with silence, and flushes instantly."""

from gateway.playback import PlaybackBuffer


def test_take_returns_exact_frame_and_consumes():
    pb = PlaybackBuffer(sample_rate=48_000)
    pb.enqueue(b"\x10\x00" * 100)  # 100 samples
    out = pb.take(50)
    assert len(out) == 100          # 50 samples * 2 bytes
    assert len(pb) == 50


def test_take_pads_with_silence_when_short():
    pb = PlaybackBuffer(sample_rate=48_000)
    pb.enqueue(b"\x10\x00" * 30)    # only 30 samples
    out = pb.take(100)              # ask for 100
    assert len(out) == 200          # padded to 100 samples
    assert out.endswith(b"\x00" * 140)  # 70 samples of silence
    assert len(pb) == 0


def test_flush_drops_everything():
    pb = PlaybackBuffer(sample_rate=48_000)
    pb.enqueue(b"\xff" * 4096)
    assert len(pb) > 0
    pb.flush()
    assert len(pb) == 0
    # A take after flush is pure silence.
    assert pb.take(10) == b"\x00" * 20
