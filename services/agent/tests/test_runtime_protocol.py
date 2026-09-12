"""The wire protocol. Both sides share this file, so both sides break together."""

import base64

import pytest

from zeg.runtime import protocol as p


def test_the_frame_rates_divide_exactly():
    # The whole design rests on this: one 80 ms model frame is exactly four 20 ms
    # transport frames at both rates, so nothing has to be repacketized and no
    # drift accumulates over a call.
    assert p.INPUT_FRAME_SAMPLES == 1280
    assert p.OUTPUT_FRAME_SAMPLES == 1764
    assert p.INPUT_FRAME_SAMPLES % 4 == 0
    assert p.OUTPUT_FRAME_SAMPLES % 4 == 0
    assert p.OUTPUT_FRAME_SAMPLES // 4 == p.OUTPUT_SAMPLE_RATE * 20 // 1000


def test_the_session_cap_is_sixteen_minutes():
    assert p.MAX_SESSION_FRAMES * p.FRAME_MS / 60000.0 == 16.0


def test_event_ids_are_ordered_and_prefixed():
    wire = p.Wire("c")
    ids = [wire.stop()["event_id"] for _ in range(3)]
    assert ids == ["c_1", "c_2", "c_3"]


def test_input_audio_round_trips():
    wire = p.Wire()
    pcm = b"\x01\x02" * p.INPUT_FRAME_SAMPLES
    msg = wire.audio(pcm)
    assert p.decode_input_audio(msg) == pcm


def test_output_audio_round_trips():
    wire = p.Wire("s")
    pcm = b"\x03\x04" * p.OUTPUT_FRAME_SAMPLES
    msg = wire.response_audio("r1", pcm, frame=7)
    assert p.decode_output_audio(msg) == pcm
    assert msg["frame"] == 7


def test_a_short_frame_is_refused_on_the_way_out():
    with pytest.raises(p.ProtocolError):
        p.Wire().audio(b"\x00" * 10)


def test_a_short_frame_is_refused_on_the_way_in():
    msg = {
        "type": p.AUDIO,
        "encoding": "pcm16",
        "sample_rate": p.INPUT_SAMPLE_RATE,
        "channels": 1,
        "audio": base64.b64encode(b"\x00" * 64).decode("ascii"),
    }
    with pytest.raises(p.ProtocolError):
        p.decode_input_audio(msg)


def test_the_wrong_sample_rate_is_refused():
    msg = dict(p.Wire().audio(b"\x00" * p.INPUT_FRAME_BYTES), sample_rate=8000)
    with pytest.raises(p.ProtocolError):
        p.decode_input_audio(msg)


def test_stereo_is_refused():
    msg = dict(p.Wire().audio(b"\x00" * p.INPUT_FRAME_BYTES), channels=2)
    with pytest.raises(p.ProtocolError):
        p.decode_input_audio(msg)


def test_a_corrupt_payload_is_refused_rather_than_played():
    msg = dict(p.Wire().audio(b"\x00" * p.INPUT_FRAME_BYTES), audio="not base64!!")
    with pytest.raises(p.ProtocolError):
        p.decode_input_audio(msg)


def test_binary_frames_are_refused():
    # One framing on this socket. A second, undocumented one is how protocols rot.
    with pytest.raises(p.ProtocolError):
        p.parse(b'{"type":"session.stop"}')


def test_malformed_json_is_refused():
    with pytest.raises(p.ProtocolError):
        p.parse("{not json")


def test_a_message_needs_a_type():
    with pytest.raises(p.ProtocolError):
        p.parse('{"event_id":"x"}')


def test_parse_round_trips_a_built_message():
    msg = p.Wire().turn_start(1, preroll_frames=2)
    assert p.parse(p.dumps(msg)) == msg


def test_turn_numbers_start_at_one():
    with pytest.raises(p.ProtocolError):
        p.Wire().turn_start(0)
    with pytest.raises(p.ProtocolError):
        p.Wire().turn_commit(0)


def test_version_mismatch_is_loud():
    good = p.Wire("s").ready("s1", {})
    p.check_version(good)
    with pytest.raises(p.ProtocolError):
        p.check_version({"protocol": {"name": p.PROTOCOL_NAME, "version": 99}})
    with pytest.raises(p.ProtocolError):
        p.check_version({"protocol": {"name": "something.else", "version": 1}})


def test_an_unknown_response_status_is_refused():
    with pytest.raises(p.ProtocolError):
        p.Wire("s").response_done("r1", "finished-ish", "reason")


def test_splitting_an_output_frame_is_lossless():
    pcm = bytes(range(256)) * 14  # 3584 bytes, divisible by 8
    parts = p.split_output_frame(pcm, 4)
    assert len(parts) == 4
    assert b"".join(parts) == pcm
    assert len({len(part) for part in parts}) == 1


def test_splitting_refuses_an_uneven_frame():
    with pytest.raises(p.ProtocolError):
        p.split_output_frame(b"\x00" * 10, 4)
