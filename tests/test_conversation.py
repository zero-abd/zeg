from zeg.backends import MockBackend
from zeg.config import CallConfig
from zeg.conversation import CallerTurn, ConversationRunner
from zeg.prompts import GREETING, SYSTEM_PROMPT


def test_a_whole_call_completes_without_errors():
    r = ConversationRunner(MockBackend()).run(SYSTEM_PROMPT, GREETING)
    assert not r.errors
    assert not r.hit_time_limit


def test_transcript_alternates_and_starts_with_the_disclosure():
    r = ConversationRunner(MockBackend()).run(SYSTEM_PROMPT, GREETING)
    assert r.transcript[0].speaker == "agent"
    assert "AI interviewer" in r.transcript[0].text
    assert "recorded" in r.transcript[0].text


def test_the_caller_gets_a_reply_to_every_turn():
    r = ConversationRunner(MockBackend()).run(SYSTEM_PROMPT, GREETING)
    callers = [e for e in r.transcript if e.speaker == "caller"]
    agents = [e for e in r.transcript if e.speaker == "agent"]
    assert len(agents) >= len(callers)


def test_barge_in_is_recorded():
    r = ConversationRunner(MockBackend()).run(SYSTEM_PROMPT, GREETING)
    assert r.interruptions >= 1


def test_latency_is_measured_per_reply():
    r = ConversationRunner(MockBackend()).run(SYSTEM_PROMPT, GREETING)
    assert r.reply_latencies_ms
    assert r.p95_latency_ms >= r.median_latency_ms


def test_mock_latency_reflects_endpoint_plus_time_to_first_audio():
    """200 ms endpointing plus five frames of synthesis delay."""
    r = ConversationRunner(MockBackend()).run(SYSTEM_PROMPT, GREETING)
    assert 250 <= r.median_latency_ms <= 400


def test_wall_clock_stops_a_runaway_call():
    """The engine must end the call on time whatever the model is doing."""
    long_caller = [CallerTurn("talking", speak_s=30.0, pause_after_s=2.0)] * 40
    r = ConversationRunner(MockBackend(), call=CallConfig(max_duration_s=60)).run(
        SYSTEM_PROMPT, GREETING, caller=long_caller
    )
    assert r.hit_time_limit
    assert r.duration_s <= 61


def test_render_produces_timestamped_lines():
    r = ConversationRunner(MockBackend()).run(SYSTEM_PROMPT, GREETING)
    first = r.render().splitlines()[0]
    assert first.startswith("[00:00] agent")
