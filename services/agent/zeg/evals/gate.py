"""What the voice gate does with sounds that are not speech.

The gate decides two things that a candidate hears immediately: when the agent stops
talking because they started, and when their turn is over. It decides both from the
loudness of a 20 ms frame.

That is a thin basis for a decision this audible. A cough, a door, a keyboard, a dog,
someone else's voice in the next room — all of them are loud frames. So is a candidate
who speaks quietly, right up until they are not.

These probes feed the gate sounds with a known shape and report what it did. Nothing
here needs a GPU or a microphone; the gate is pure arithmetic over frames.
"""

import collections
from dataclasses import dataclass
from typing import List, Optional

from ..audio import AudioFrame, tone
from ..backends.base import AgentInterrupted
from ..backends.gb10 import GB10Config, GB10Session
from ..config import AudioConfig
from ..runtime import protocol as p


class _Loopback:
    """The smallest thing that satisfies the link interface."""

    def __init__(self):
        self.sent = []
        self.closed = False
        self._inbox = collections.deque()
        wire = p.Wire("srv")
        self._ready = [wire.ready("s1", {}), wire.configured("s1", {})]

    def send(self, msg):
        self.sent.append(msg)
        if msg["type"] == p.CONFIGURE:
            self._inbox.extend(self._ready)

    def drain(self):
        out = list(self._inbox)
        self._inbox.clear()
        return out

    def close(self):
        self.closed = True

    def turn_starts(self) -> int:
        return sum(1 for m in self.sent if m["type"] == p.TURN_START)


@dataclass
class Probe:
    name: str
    what_it_is: str
    #: Frame amplitudes, one per 20 ms. Zero is silence.
    amplitudes: List[float]
    should_open_turn: bool
    should_interrupt: bool


def _burst(level: float, frames: int) -> List[float]:
    return [level] * frames


SPEECH = 0.30
QUIET_SPEECH = 0.05
ROOM_TONE = 0.015

PROBES = (
    Probe(
        name="sustained_speech",
        what_it_is="Someone talking for a second.",
        amplitudes=_burst(SPEECH, 50),
        should_open_turn=True,
        should_interrupt=True,
    ),
    Probe(
        name="cough",
        what_it_is="One loud frame. A cough, a door, a keyboard.",
        amplitudes=_burst(SPEECH, 1) + _burst(0.0, 40),
        should_open_turn=False,
        should_interrupt=False,
    ),
    Probe(
        name="knock",
        what_it_is="Two loud frames, 40 ms. Still not a word.",
        amplitudes=_burst(SPEECH, 2) + _burst(0.0, 40),
        should_open_turn=False,
        should_interrupt=False,
    ),
    Probe(
        name="room_tone",
        what_it_is="Constant quiet background, below anyone speaking.",
        amplitudes=_burst(ROOM_TONE, 60),
        should_open_turn=False,
        should_interrupt=False,
    ),
    Probe(
        name="quiet_speaker",
        what_it_is="A soft voice, well above room tone and well below a shout.",
        amplitudes=_burst(QUIET_SPEECH, 50),
        should_open_turn=True,
        should_interrupt=True,
    ),
)


@dataclass
class GateResult:
    probe: Probe
    opened_turn: bool
    interrupted: bool

    @property
    def correct(self) -> bool:
        return (self.opened_turn == self.probe.should_open_turn
                and self.interrupted == self.probe.should_interrupt)

    @property
    def failure(self) -> Optional[str]:
        if self.correct:
            return None
        if self.interrupted and not self.probe.should_interrupt:
            return "cut the agent off mid-sentence"
        if not self.interrupted and self.probe.should_interrupt:
            return "did not yield when the candidate spoke"
        if self.opened_turn and not self.probe.should_open_turn:
            return "opened a turn on a noise"
        return "never heard the candidate at all"


@dataclass
class GateReport:
    results: List[GateResult]

    @property
    def clean(self) -> bool:
        return all(r.correct for r in self.results)

    def render(self) -> str:
        out = ["%d probes at the voice gate" % len(self.results), ""]
        for r in self.results:
            mark = "ok  " if r.correct else "FAIL"
            out.append("  %s %-18s turn=%-5s interrupt=%-5s"
                       % (mark, r.probe.name, r.opened_turn, r.interrupted))
            if not r.correct:
                out.append("       %s" % r.probe.what_it_is)
                out.append("       %s" % r.failure)
        out.append("")
        out.append("verdict       %s"
                   % ("the gate tells speech from noise"
                      if self.clean else
                      "the gate is reacting to loudness, not to speech"))
        return "\n".join(out)


def _run_probe(probe: Probe, config: Optional[GB10Config] = None) -> GateResult:
    audio = AudioConfig()
    link = _Loopback()
    sess = GB10Session(link, "be brief", audio=audio, config=config or GB10Config())
    # Put the agent mid-utterance so an interruption has something to interrupt.
    sess._response_id = "r1"

    interrupted = False
    for level in probe.amplitudes:
        frame = (
            tone(audio.input_sample_rate, audio.input_frame_samples, amplitude=level)
            if level > 0
            else AudioFrame.silence(audio.input_sample_rate, audio.input_frame_samples)
        )
        sess.push_audio(frame)
        for ev in sess.poll():
            if isinstance(ev, AgentInterrupted):
                interrupted = True
    return GateResult(probe, link.turn_starts() > 0, interrupted)


def run_gate(config: Optional[GB10Config] = None) -> GateReport:
    return GateReport([_run_probe(pr, config) for pr in PROBES])
