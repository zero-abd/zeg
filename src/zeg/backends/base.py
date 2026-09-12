"""The backend contract.

One interface, two implementations: a mock that runs anywhere, and the real
Nemotron VoiceChat model on a GB10 box.

The interface is full-duplex on purpose. VoiceChat listens and speaks at the same
time, so there is no "now it is the agent's turn" state to model. Audio goes in
continuously; events come out whenever the model has something to say. Anything
that assumes strict turn-taking belongs above this layer, not inside it.
"""

import abc
from dataclasses import dataclass
from typing import Iterator, List, Optional

from ..audio import AudioFrame


# --- Events the backend emits ------------------------------------------------


@dataclass
class AgentAudio:
    """A frame of synthesised agent speech, ready to send to the caller."""

    frame: AudioFrame


@dataclass
class AgentText:
    """What the agent is saying, in text.

    VoiceChat emits this alongside the audio, so it is a record of what was actually
    spoken rather than a separate transcription of it.
    """

    text: str
    final: bool = False


@dataclass
class UserTranscript:
    """What the caller said, as the model heard it.

    `final` distinguishes a stable transcript from a partial hypothesis. Partials
    drive endpointing; finals go in the record.
    """

    text: str
    final: bool = False


@dataclass
class AgentInterrupted:
    """The model stopped speaking because the caller started.

    Anything already queued for playback must be dropped on this event, or the caller
    hears the agent talk over them.
    """

    reason: str = "barge_in"


@dataclass
class BackendError:
    message: str
    fatal: bool = True


BackendEvent = object  # one of the dataclasses above


# --- The session -------------------------------------------------------------


class VoiceSession(abc.ABC):
    """One call. Not reusable and not thread-safe."""

    @abc.abstractmethod
    def push_audio(self, frame: AudioFrame) -> None:
        """Feed one frame of caller audio. Non-blocking."""

    @abc.abstractmethod
    def poll(self) -> Iterator[BackendEvent]:
        """Drain whatever the model has produced since the last call.

        Returns immediately, possibly empty. The caller drives the clock by pushing
        audio, so a poll that yields nothing means the model is still listening.
        """

    @abc.abstractmethod
    def close(self) -> None:
        """Release the session. Safe to call twice."""

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class VoiceBackend(abc.ABC):
    """Loads the model once, serves many sessions.

    Construction is expensive and happens at process start. Nothing loads a model
    during a call.
    """

    name = "base"

    @abc.abstractmethod
    def start_session(
        self,
        system_prompt: str,
        greeting: Optional[str] = None,
    ) -> VoiceSession:
        """Open a call.

        `greeting` is spoken before any caller audio arrives. It carries the AI
        disclosure and the recording-consent request, both of which are mandatory
        and must not be left to the model to remember. See docs/06-compliance.md.
        """

    def warmup(self) -> None:
        """Run a throwaway inference so the first real call is not the slow one."""

    def close(self) -> None:
        """Free the model."""


def collect_text(events: List[BackendEvent]) -> str:
    """Join the final agent text out of a batch of events. Test helper."""
    return "".join(e.text for e in events if isinstance(e, AgentText) and e.final)
