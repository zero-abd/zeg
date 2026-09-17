"""Call limits, and the room they have to leave for the lines that close a call."""

import pytest

from zeg.config import CallConfig

@pytest.mark.parametrize("call_kwargs, wrap_up", [
    ({"max_duration_s": 900}, 810.0),                    # the ordinary call is unchanged
    ({"max_duration_s": 600}, 510.0),
])
def test_the_usual_calls_keep_their_wrap_up(call_kwargs, wrap_up):
    assert CallConfig(**call_kwargs).wrap_up_at_s == wrap_up


@pytest.mark.parametrize("call_kwargs", [
    {"max_duration_s": 900, "wrap_up_at_s": 899},   # never wrapped up at all
    {"max_duration_s": 30},                          # wrapped up two seconds before goodbye
])
def test_the_wrap_up_leaves_room_for_itself_and_the_goodbye(call_kwargs):
    """A 900 second call asked to wrap up at 899 reached the goodbye first and never
    wrapped up; a 30 second call cut its own wrap-up off after two seconds."""
    from zeg.prompts import TIME_UP, WRAP_UP, speech_seconds

    call = CallConfig(**call_kwargs)
    room = call.max_duration_s - call.wrap_up_at_s
    assert room >= speech_seconds(WRAP_UP) + speech_seconds(TIME_UP)
