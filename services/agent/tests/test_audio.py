import math

import pytest

from zeg.audio import AudioFrame, resample_linear, rms, tone


def test_frame_rejects_odd_byte_count():
    with pytest.raises(ValueError):
        AudioFrame(b"\x00", 16000)


def test_duration_matches_sample_count():
    f = AudioFrame.silence(16000, 320)
    assert f.n_samples == 320
    assert f.duration_s == pytest.approx(0.02)


def test_silence_is_quiet_and_tone_is_not():
    assert rms(AudioFrame.silence(16000, 320)) == 0.0
    assert rms(tone(16000, 320, amplitude=0.5)) > 0.2


def test_resample_changes_rate_and_length_not_duration():
    src = tone(8000, 160)
    out = resample_linear(src, 16000)
    assert out.sample_rate == 16000
    assert out.n_samples == 320
    assert out.duration_s == pytest.approx(src.duration_s)


def test_resample_to_same_rate_is_identity():
    src = tone(16000, 320)
    assert resample_linear(src, 16000) is src


def test_a_constant_offset_is_not_loudness():
    """A capture path with a DC offset counted the bias itself as sound. An offset of 700
    crossed the speech threshold, so a silent line read as someone talking."""
    assert rms(AudioFrame.from_samples([700] * 320, 16000)) == 0.0
    assert rms(AudioFrame.from_samples([-1200] * 320, 16000)) == 0.0


def test_an_offset_does_not_change_how_loud_a_signal_is():
    plain = tone(16000, 320, amplitude=0.3)
    biased = AudioFrame.from_samples([v + 700 for v in plain.samples()], 16000)
    assert rms(biased) == pytest.approx(rms(plain), abs=0.002)


def test_telephony_upsample_preserves_a_low_tone():
    """8 kHz is what the PSTN gives us and 16 kHz is what the model wants."""
    src = tone(8000, 800, freq_hz=300.0, amplitude=0.5)
    out = resample_linear(src, 16000)
    assert rms(out) == pytest.approx(rms(src), abs=0.02)
