"""How long the fixed lines take to say.

The estimate behind every timing margin: the consent timers hold until a line of ours has
been said, and the wrap-up mark leaves room for the wrap-up and the goodbye. An estimate
that reads short means one line spoken over another, so this measures the lines rather
than trusting the number.

Synthesised with whatever voice this machine has, which is not the box's. It still catches
the two things that matter: a line added or reworded until it outruns the estimate, and the
rate being raised past what speech actually does.
"""

import pytest

from zeg.config import AudioConfig
from zeg.prompts import (
    CLOSING,
    CONSENT_REASK,
    GREETING,
    TIME_UP,
    WRAP_UP,
    speech_seconds,
)

#: The lines the timing margins are built from.
TIMED_LINES = {
    "GREETING": GREETING,
    "CONSENT_REASK": CONSENT_REASK,
    "WRAP_UP": WRAP_UP,
    "TIME_UP": TIME_UP,
    "CLOSING": CLOSING,
}


@pytest.fixture(scope="module")
def spoken():
    """Every timed line synthesised once. Skipped where no voice is installed."""
    from zeg.backends.tts import _which_engine, synth_frames

    engine = _which_engine()
    if engine is None:
        pytest.skip("no speech engine on this machine")
    audio = AudioConfig()
    return {
        name: sum(f.duration_s for f in synth_frames(text, audio, engine))
        for name, text in TIMED_LINES.items()
    }


@pytest.mark.parametrize("name", sorted(TIMED_LINES))
def test_the_estimate_is_never_shorter_than_the_line_takes_to_say(name, spoken):
    estimate = speech_seconds(TIMED_LINES[name])
    assert estimate >= spoken[name], (
        "%s takes %.1f s to say and is estimated at %.1f s, so a timer will speak over it"
        % (name, spoken[name], estimate)
    )
