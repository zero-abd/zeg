"""The speech runtime: the model process that the GB10 backend talks to.

Only `protocol` is imported here. It is pure stdlib and both sides of the socket
need it, so importing `zeg.runtime` on a laptop must stay free. Everything that
touches torch, CUDA or a WebSocket library lives behind a function-level import in
`model`, `loop` and `server`, and importing those modules on a machine without a
GPU is fine; *running* them is not.

See docs/11-runtime.md for the design and for what is untested.
"""

from . import protocol

__all__ = ["protocol"]
