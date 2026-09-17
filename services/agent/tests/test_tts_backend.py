

def test_a_wedged_voice_does_not_hang_the_call(tmp_path, monkeypatch):
    """A system voice held a synthesis process for 28 minutes and hung the whole test
    suite: there was no timeout, so the fallback tone could never be reached."""
    import time

    from zeg.backends import tts
    from zeg.config import AudioConfig

    hanging = tmp_path / "hangs"
    hanging.write_text("#!/bin/sh\nsleep 30\n")
    hanging.chmod(0o755)
    monkeypatch.setattr(tts, "TTS_TIMEOUT_S", 0.5)

    started = time.monotonic()
    frames = tts.synth_frames("we cut p99 to 30 ms", AudioConfig(), str(hanging))
    elapsed = time.monotonic() - started

    assert frames, "the fallback tone is what keeps the call going"
    assert elapsed < 5, "waited %.1f s for a wedged voice" % elapsed


def test_a_failed_line_leaves_no_temporary_file_behind(tmp_path, monkeypatch):
    import glob
    import tempfile

    from zeg.backends import tts
    from zeg.config import AudioConfig

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    failing = tmp_path / "fails"
    failing.write_text("#!/bin/sh\nexit 1\n")
    failing.chmod(0o755)

    tts.synth_frames("hello", AudioConfig(), str(failing))
    assert glob.glob(str(tmp_path / "*.wav")) == []
