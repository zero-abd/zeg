import pytest

from zeg.backends.base import UserTranscript
from zeg.interview import Interview, Rollover
from zeg.memory import RolloverPolicy, SessionSeed, last_exchange
from zeg.interview import Turn


@pytest.fixture
def policy():
    return RolloverPolicy()


# --- when to roll -------------------------------------------------------------


def test_never_rolls_away_from_a_turn_boundary(policy):
    """Mid-response the model is mid-sentence. Swapping there is audible."""
    assert not policy.should_roll(session_age_s=999, at_turn_boundary=False)


def test_rolls_once_past_the_context_horizon(policy):
    assert policy.should_roll(session_age_s=101, at_turn_boundary=True)


def test_does_not_roll_before_the_horizon(policy):
    assert not policy.should_roll(session_age_s=60, at_turn_boundary=True)


def test_will_not_thrash_on_a_fresh_session(policy):
    """Guards the pathological case where every turn triggers a rollover."""
    assert not policy.should_roll(session_age_s=10, at_turn_boundary=True)


def test_waits_for_a_probe_ladder_to_finish(policy):
    """Mid-ladder is the thread a fresh session would lose."""
    assert not policy.should_roll(
        session_age_s=200, at_turn_boundary=True, probe_in_progress=True
    )


def test_frame_pressure_rolls_even_inside_the_horizon(policy):
    used = int(policy.frame_budget * 0.85)
    assert policy.should_roll(session_age_s=60, at_turn_boundary=True, frames_used=used)


def test_frame_headroom_leaves_room_before_the_cap(policy):
    used = int(policy.frame_budget * 0.5)
    assert not policy.should_roll(session_age_s=60, at_turn_boundary=True, frames_used=used)


def test_the_horizon_sits_below_the_models_real_window(policy):
    """Roll before the model forgets, not as it does."""
    assert policy.context_horizon_s < 120


def test_frames_for_matches_the_frame_rate(policy):
    assert policy.frames_for(80) == 1000  # 12.5 frames a second


# --- what the new session is primed with --------------------------------------


def test_a_seed_carries_the_standing_instructions_and_the_state():
    seed = SessionSeed("SYSTEM RULES", "Elapsed 3:00. Phase: depth_one.")
    r = seed.render()
    assert "SYSTEM RULES" in r
    assert "depth_one" in r


def test_a_seed_can_carry_the_last_exchange_so_there_is_no_seam():
    seed = SessionSeed("sys", "brief", ["Interviewer: What broke?", "Candidate: A lock."])
    assert "What broke?" in seed.render()


def test_a_seed_without_an_exchange_still_renders():
    assert "brief" in SessionSeed("sys", "brief").render()


def test_last_exchange_labels_both_speakers():
    lines = last_exchange([Turn(0, "agent", "What broke?"), Turn(5, "caller", "A lock.")])
    assert lines == ["Interviewer: What broke?", "Candidate: A lock."]


def test_last_exchange_is_short_by_design():
    """Enough to continue naturally, cheap enough that the prefill is not the cost."""
    turns = [Turn(i, "caller", "line %d" % i) for i in range(20)]
    assert len(last_exchange(turns)) == 2


def test_a_very_long_turn_is_trimmed():
    long = Turn(0, "caller", "x" * 500)
    assert len(last_exchange([long])[0]) < 200


# --- rollover in a live interview ---------------------------------------------


def consented(iv, t=5.0):
    iv.start()
    iv.on_event(UserTranscript("yes that is fine", final=True), t)
    return iv


def rollovers(actions):
    return [a for a in actions if isinstance(a, Rollover)]


def test_a_short_call_never_rolls():
    iv = consented(Interview())
    actions = iv.on_event(UserTranscript("we cut latency to 30ms", final=True), 40)
    assert not rollovers(actions)
    assert iv.record.rollovers == 0


def run(iv, times, text="we cut p99 to 30ms from 400ms"):
    """Answer at each time, returning every action the interview produced."""
    out = []
    for t in times:
        out.extend(iv.on_event(UserTranscript(text, final=True), t))
    return out


def test_a_long_call_rolls_the_session():
    iv = consented(Interview())
    actions = run(iv, (200, 210, 220, 230, 240, 250))
    assert rollovers(actions), "past the horizon with no probe running, it should roll"
    assert iv.record.rollovers == 1


def test_it_holds_off_until_the_ladder_is_done():
    """Rolling mid-descent would drop the thread the interview is following."""
    iv = consented(Interview())
    mid = run(iv, (200, 210))          # two rungs in, still descending
    assert not rollovers(mid)
    assert iv.engine.probe_in_progress


def test_the_seed_carries_what_the_old_session_knew():
    iv = consented(Interview())
    actions = run(iv, (200, 210, 220, 230, 240, 250), "we cut reconciler p99 to 30ms")
    text = rollovers(actions)[0].text
    assert "reconciler" in text          # the claim
    assert "Phase" in text                # where we are
    assert "screening call" in text       # the standing rules


def test_rolling_resets_the_clock_so_it_does_not_immediately_roll_again():
    iv = consented(Interview())
    run(iv, (200, 210, 220, 230, 240, 250))
    assert iv.record.rollovers == 1
    again = run(iv, (260, 270))
    assert not rollovers(again)
    assert iv.record.rollovers == 1


def test_rollover_can_be_tuned_without_touching_the_driver():
    eager = Interview(rollover=RolloverPolicy(context_horizon_s=20, min_session_s=10))
    consented(eager)
    assert rollovers(run(eager, (30, 40, 50, 60, 70)))


def test_a_candidate_who_goes_vague_mid_ladder_does_not_switch_off_rollover():
    """Two vague answers make the engine abandon a ladder, but the rollover guard still
    counted it as in progress, and vague answers never start a new claim. So a candidate
    who went vague part way down switched rollover off for the rest of the call, and the
    model ran on far past what it can remember."""
    from zeg.backends.base import UserTranscript
    from zeg.interview import Interview, Rollover
    from zeg.memory import RolloverPolicy

    iv = Interview(rollover=RolloverPolicy(context_horizon_s=20, min_session_s=10))
    iv.start()
    iv.on_event(UserTranscript("yes that is fine", final=True), 5)
    script = [
        (30, "we rewrote the payment reconciler after an outage"),
        (40, "I wrote the advisory lock fix myself"),
        (50, "we basically did various things"),
        (60, "pretty much just stuff"),
    ] + [(t, "we basically did various things") for t in range(70, 310, 10)]

    rolled_after_the_stall = []
    for t, text in script:
        actions = iv.on_event(UserTranscript(text, final=True), t)
        if t > 60 and any(isinstance(a, Rollover) for a in actions):
            rolled_after_the_stall.append(t)
    assert rolled_after_the_stall, "rollover never fired again once the ladder stalled"
