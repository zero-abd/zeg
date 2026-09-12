"""FrameChunker emits whole 20 ms frames and never drops a sample."""

from gateway.framing import FrameChunker


def test_exact_20ms_frames_at_16k():
    ch = FrameChunker(sample_rate=16_000, frame_ms=20)
    assert ch.frame_samples == 320
    assert ch.frame_bytes == 640

    # 1.5 frames in -> 1 frame out, half a frame held back.
    frames = ch.push(b"\x01\x02" * 480)  # 480 samples = 960 bytes
    assert len(frames) == 1
    assert frames[0].n_samples == 320
    assert frames[0].sample_rate == 16_000
    assert ch.pending_samples == 160

    # Another 1.5 frames -> the held 160 + 480 = 640 samples = 2 frames.
    frames = ch.push(b"\x01\x02" * 480)
    assert len(frames) == 2
    assert ch.pending_samples == 0


def test_timestamps_advance_by_frame_duration():
    ch = FrameChunker(sample_rate=16_000, frame_ms=20)
    frames = ch.push(b"\x00\x00" * 320 * 3)  # exactly 3 frames
    assert [round(f.timestamp_s, 3) for f in frames] == [0.0, 0.02, 0.04]


def test_byte_stream_reassembles_across_odd_pushes():
    ch = FrameChunker(sample_rate=16_000, frame_ms=20)
    total = b""
    for _ in range(7):
        for f in ch.push(b"\xab\xcd" * 69):  # 138 bytes: whole samples, not frame-aligned
            total += f.pcm
    # Everything emitted is a whole number of frames, and no bytes are invented.
    assert len(total) % ch.frame_bytes == 0
    assert len(total) + ch.pending_samples * 2 == 7 * 138
