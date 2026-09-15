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


class LoopbackLink:
    """The real client session wired to the real server session, in memory.

    Every message is serialised with the protocol's own dumps and parsed with its own
    parse in both directions, the model is stepped by the real frame loop, and actions
    go through the server's real dispatcher. A field the two halves disagree on fails
    here instead of on the box. No socket, no thread.
    """

    def __init__(self, model=None):
        from zeg.runtime.loop import FrameLoop
        from zeg.runtime.model import SilenceModel
        from zeg.runtime.server import RuntimeServer
        from zeg.runtime.session import ServerSession

        self.model = model or SilenceModel()
        self.server = ServerSession("s1")
        self._results = collections.deque()
        self.loop = FrameLoop(self.model, self._results.append)
        # The dispatcher reads nothing from the server object, so no socket is needed.
        self._dispatcher = RuntimeServer.__new__(RuntimeServer)
        self._inbox = collections.deque()
        self.sent = []
        self.received = []
        self.closed = False
        self._to_client(self.server.ready())  # the server greets on connect

    # --- the Link interface ---------------------------------------------------

    def send(self, msg):
        self.sent.append(msg)
        for out in self.server.on_client(p.parse(p.dumps(msg))):
            if out["type"] == p.CONFIGURED:
                self.model.prefill(self.server.instructions)
            self._to_client(out)
        self._pump()

    def drain(self):
        out = list(self._inbox)
        self._inbox.clear()
        self.received.extend(out)
        return out

    def close(self):
        self.closed = True

    # --- internals ------------------------------------------------------------

    def _to_client(self, msg):
        self._inbox.append(p.parse(p.dumps(msg)))

    def _pump(self):
        """Dispatch, step the model, feed each frame back, and repeat until quiet."""
        for _ in range(10_000):
            self._dispatcher._dispatch(self.server, self.loop)
            handled = self.loop.run_pending()
            while self._results:
                for out in self.server.on_frame(self._results.popleft()):
                    self._to_client(out)
            if not handled and not self._results and not self.server.actions:
                return
        raise RuntimeError("loopback did not settle")

    # --- test helpers ---------------------------------------------------------

    def received_types(self):
        return [m["type"] for m in self.received]

    def errors(self):
        return [m for m in self.received if m["type"] == p.ERROR]
