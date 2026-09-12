"""Backend selection.

The GB10 backend is imported lazily. Importing it on a laptop would drag in torch and
the NeMo tree, neither of which is installed there, so selection stays cheap until
something actually asks for real inference.
"""

from typing import Optional

from ..config import BackendConfig
from .base import (
    AgentAudio,
    AgentInterrupted,
    AgentText,
    BackendError,
    BackendEvent,
    UserTranscript,
    VoiceBackend,
    VoiceSession,
)
from .mock import MockBackend

__all__ = [
    "AgentAudio",
    "AgentInterrupted",
    "AgentText",
    "BackendError",
    "BackendEvent",
    "MockBackend",
    "UserTranscript",
    "VoiceBackend",
    "VoiceSession",
    "build_backend",
]


def build_backend(config: Optional[BackendConfig] = None) -> VoiceBackend:
    config = config or BackendConfig()
    if config.kind == "mock":
        return MockBackend(audio=config.audio)
    if config.kind == "gb10":
        from .gb10 import GB10Backend  # noqa: WPS433 - deliberate lazy import

        return GB10Backend(config)
    raise ValueError("unknown backend kind: %r" % config.kind)
