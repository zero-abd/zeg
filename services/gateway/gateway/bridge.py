"""The transport-agnostic core: caller audio in, agent events out.

This is `conversation.py::_consume` for a real call. It owns a `VoiceSession`,
pushes one caller frame at a time, and drains whatever the model produced. It
knows nothing about WebRTC, so it can be driven by the WebRTC adapter in
production and by synthetic frames in a test, unchanged.

It does not run a clock. The stream of inbound audio frames *is* the clock: the
model is duplex and advances one step per frame it hears, exactly as in
conversation.py. The transport pushes real audio (silence included) at real
time, so the agent's replies come back paced to real time for free.
"""

from typing import Callable, List, Optional, Tuple

from zeg.audio import AudioFrame
from zeg.backends import (
    AgentAudio,
    AgentInterrupted,
    AgentText,
    BackendError,
    UserTranscript,
    VoiceSession,
)


class CallBridge:
    """Drives one VoiceSession for the length of one call.

    `on_agent_audio` receives each synthesised agent frame (the transport queues
    it for playback). `on_interrupt` fires on barge-in and must drop any queued
    playback. Both default to no-ops so the bridge is usable in a test with no
    transport attached.
    """

    def __init__(
        self,
        session: VoiceSession,
        on_agent_audio: Optional[Callable[[AudioFrame], None]] = None,
        on_interrupt: Optional[Callable[[], None]] = None,
    ) -> None:
        self.session = session
        self.on_agent_audio = on_agent_audio or (lambda frame: None)
        self.on_interrupt = on_interrupt or (lambda: None)

        self.transcript: List[Tuple[str, str]] = []   # (speaker, text), speaker in {agent, caller}
        self.interruptions = 0
        self.agent_audio_s = 0.0
        self.error: Optional[str] = None

    def feed(self, frame: AudioFrame) -> None:
        """Push one caller frame and dispatch everything it shook loose."""
        self.session.push_audio(frame)
        for ev in self.session.poll():
            self._dispatch(ev)

    def _dispatch(self, ev) -> None:
        if isinstance(ev, AgentAudio):
            self.agent_audio_s += ev.frame.duration_s
            self.on_agent_audio(ev.frame)
        elif isinstance(ev, AgentInterrupted):
            # Barge-in. Drop queued playback now; a late flush is an agent that
            # keeps talking over the candidate for a beat, which is what everyone
            # notices first.
            self.interruptions += 1
            self.on_interrupt()
        elif isinstance(ev, AgentText):
            if ev.final:
                self.transcript.append(("agent", ev.text))
        elif isinstance(ev, UserTranscript):
            if ev.final:
                self.transcript.append(("caller", ev.text))
        elif isinstance(ev, BackendError):
            # Fatal by default (see base.py). The call layer tears down playback
            # and the agent apologises and hangs up; here we just record it.
            self.error = ev.message

    def close(self) -> None:
        self.session.close()
