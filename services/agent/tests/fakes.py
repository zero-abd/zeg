"""Test doubles shared across test files.

The fake link used to live inside the real backend's own test file, which kept every
other suite from running that backend at all. That is how the backends came to be kept
in step by tests copied between files instead of one shared contract, and the copies
drifted.
"""

import collections

from zeg.runtime import protocol as p


class FakeLink:
    """A connection that is two lists.

    Records what the session sent and lets a test hand back whatever the runtime
    would have said. No thread, no socket, no clock, so every test that uses it is
    deterministic and runs in microseconds.
    """

    def __init__(self, auto_ready=True):
        self.sent = []
        self.closed = False
        self.auto_ready = auto_ready
        self.wire = p.Wire("srv")
        self._inbox = collections.deque()

    # --- the Link interface ---------------------------------------------------

    def send(self, msg):
        self.sent.append(msg)
        if self.auto_ready and msg["type"] == p.CONFIGURE:
            self.deliver(self.wire.ready("s1", {}))
            self.deliver(self.wire.configured("s1", {}))

    def drain(self):
        out = list(self._inbox)
        self._inbox.clear()
        return out

    def close(self):
        self.closed = True

    # --- test helpers ---------------------------------------------------------

    def deliver(self, msg):
        self._inbox.append(msg)

    def types(self):
        return [m["type"] for m in self.sent]

    def of_type(self, kind):
        return [m for m in self.sent if m["type"] == kind]


def agent_frame(link, response_id="r1", frame=1):
    """One 80 ms frame of agent audio, as the runtime would send it."""
    return link.wire.response_audio(response_id, b"\x11\x22" * p.OUTPUT_FRAME_SAMPLES, frame)
