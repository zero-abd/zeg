"""What the voice gate does with sounds that are not speech.

The gate decides, from the loudness of a 20 ms frame, when the agent must stop talking
and when a turn is over. Both are immediately audible to the candidate, and loudness is
a thin basis for either. A cough, a door, a keyboard and a dog are all loud frames.
"""

import pytest

from zeg.backends.gb10 import GB10Config
from zeg.evals.gate import PROBES, run_gate


def test_the_gate_tells_speech_from_noise():
    r = run_gate()
    assert r.clean, r.render()


@pytest.mark.parametrize("probe", PROBES, ids=lambda p: p.name)
def test_each_probe_behaves(probe):
    result = next(r for r in run_gate().results if r.probe.name == probe.name)
    assert result.correct, "%s: %s" % (probe.what_it_is, result.failure)


def test_a_cough_no_longer_cuts_the_agent_off():
    """One loud frame used to stop the agent mid-sentence. In a real call that is a
    door, a keyboard, or someone clearing their throat."""
    cough = next(r for r in run_gate().results if r.probe.name == "cough")
    assert not cough.interrupted
    assert not cough.opened_turn


def test_a_person_starting_to_talk_still_stops_the_agent():
    """The fix must not buy quiet at the cost of talking over people."""
    speech = next(r for r in run_gate().results if r.probe.name == "sustained_speech")
    assert speech.interrupted


def test_a_quiet_voice_is_still_heard():
    """Requiring persistence must not become requiring volume."""
    quiet = next(r for r in run_gate().results if r.probe.name == "quiet_speaker")
    assert quiet.opened_turn and quiet.interrupted


def test_room_tone_never_opens_a_turn():
    assert not next(r for r in run_gate().results if r.probe.name == "room_tone").opened_turn


def test_the_persistence_requirement_is_tunable():
    """Every number in the gate needs the box. This one has to be movable without
    touching the gate itself."""
    impatient = run_gate(config=GB10Config(min_speech_frames=1))
    cough = next(r for r in impatient.results if r.probe.name == "cough")
    assert cough.interrupted, "with no persistence required, the old behaviour returns"


def test_sixty_milliseconds_is_the_default_patience():
    assert GB10Config().min_speech_frames == 3
