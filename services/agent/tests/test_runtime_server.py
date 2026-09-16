"""The server's connection lifecycle, with a fake socket and a stub model.

Weights load once and serve every session. A rollover opens a new connection, so the
second connection of a process is the ordinary case rather than an edge one, and this
is the only place it is exercised: the loopback tests wire a client session straight to
a server session and never go through the connection handler.
"""

import asyncio
import time

from zeg.runtime import protocol as p
from zeg.runtime.server import RuntimeServer
from zeg.runtime.session import FrameResult


class StubModel:
    """A model that records what the server asked of it."""

    def __init__(self, reset_error=None):
        self.steps = 0
        self.resets = 0
        self.prefills = []
        self.closed = False
        self._reset_error = reset_error

    def step(self, pcm):
        if self.closed:
            raise RuntimeError("step after the model was released")
        self.steps += 1
        return FrameResult(audio_pcm=b"", audible=False)

    def commit_turn(self):
        pass

    def cancel_response(self, reason):
        pass

    def inject_context(self, text):
        pass

    def speak_text(self, text):
        pass

    def prefill(self, instructions):
        self.prefills.append(instructions)

    def reset(self):
        self.resets += 1
        if self._reset_error is not None:
            raise self._reset_error

    def close(self):
        self.closed = True


class FakeWS:
    """Hands over a fixed script of client messages and records what was sent back.

    After the script it waits, briefly, for `until` to come true, because the model
    runs on the frame loop's own thread and the connection would otherwise close
    before it had stepped.
    """

    def __init__(self, messages, until=None):
        self._messages = list(messages)
        self._until = until
        self.sent = []
        self.closed_with = None

    def __aiter__(self):
        async def script():
            for msg in self._messages:
                yield msg
                await asyncio.sleep(0)
            deadline = time.monotonic() + 2.0
            while self._until is not None and not self._until():
                if time.monotonic() > deadline:
                    break
                await asyncio.sleep(0.005)

        return script()

    async def send(self, raw):
        self.sent.append(p.parse(raw))

    async def close(self, code=None, reason=""):
        self.closed_with = (code, reason)


def a_call(frames=3):
    wire = p.Wire("client")
    out = [p.dumps(wire.configure("be brief"))]
    out += [p.dumps(wire.audio(b"\x00" * p.INPUT_FRAME_BYTES)) for _ in range(frames)]
    return out


def a_server(model):
    server = RuntimeServer.__new__(RuntimeServer)
    server.model = model
    server.host, server.port = "127.0.0.1", 0
    server.allow_silence = True
    server.max_session_frames = p.MAX_SESSION_FRAMES
    server._busy = False
    server._sessions = 0
    return server


def serve(server, ws):
    asyncio.run(server._handle(ws))
    return ws


def test_a_session_ending_does_not_release_the_weights():
    model = StubModel()
    server = a_server(model)
    serve(server, FakeWS(a_call(), until=lambda: model.steps >= 3))
    assert not model.closed, "the weights are loaded once and serve every session"
    assert model.resets == 1, "the conversation is cleared instead"


def test_a_second_session_still_gets_a_working_model():
    """A rollover is a new connection. The model was released when the first session
    ended and nothing reloads it, so every session after the first — every rollover on
    a long call — stepped a model that had been unloaded."""
    model = StubModel()
    server = a_server(model)
    serve(server, FakeWS(a_call(), until=lambda: model.steps >= 3))
    first = model.steps
    ws = serve(server, FakeWS(a_call(), until=lambda: model.steps >= first + 3))

    assert model.steps > first, "the second session never stepped the model"
    assert model.prefills == ["be brief", "be brief"]
    assert not [m for m in ws.sent if m["type"] == p.ERROR]


def test_a_model_that_fails_on_a_fixed_line_tells_the_client():
    """No audio is in flight, so no frame result arrives, and the failure was only ever
    noticed by whoever next looked at the loop. The client was told nothing: it sat in
    silence until its own watchdog fired, and reported the runtime as having gone quiet
    rather than the model as having failed."""

    class WedgedSynthesis(StubModel):
        def speak_text(self, text):
            raise RuntimeError("synthesis is wedged")

    model = WedgedSynthesis()
    server = a_server(model)
    wire = p.Wire("client")
    ws = FakeWS([p.dumps(wire.configure("be brief")),
                 p.dumps(wire.say("Is that okay with you?"))])
    ws._until = lambda: any(m["type"] == p.CLOSED for m in ws.sent)
    serve(server, ws)

    closed = [m for m in ws.sent if m["type"] == p.CLOSED]
    assert closed, "the client was never told the model had failed"
    assert closed[0]["status"] == "failed"
    assert closed[0]["reason"] == "model_error"


def test_a_session_that_fails_outright_still_tells_the_client():
    """Prefill failing is the likeliest first failure on the box: it is one of the
    seams that is not wired up. The handler raised, the client had been sent nothing
    but the handshake, and nobody closed the socket, so it waited out its own watchdog
    and reported the runtime as quiet."""

    class PrefillRaises(StubModel):
        def prefill(self, instructions):
            raise RuntimeError("prompt prefill is not wired up yet")

    model = PrefillRaises()
    server = a_server(model)
    ws = serve(server, FakeWS(a_call()))

    errors = [m for m in ws.sent if m["type"] == p.ERROR]
    closed = [m for m in ws.sent if m["type"] == p.CLOSED]
    assert errors and errors[0]["error"]["fatal"] is True
    assert "prefill" in errors[0]["error"]["message"]
    assert closed and closed[0]["status"] == "failed"
    assert ws.closed_with == (p.CLOSE_NORMAL, "session error")
    assert not server._busy, "the server is free to serve the next call"


def test_closing_the_server_releases_the_model():
    model = StubModel()
    server = a_server(model)
    server.close()
    assert model.closed
    assert server.model is None


def test_a_reset_that_fails_stops_the_process_serving():
    """The model's state is unknown after a failed reset, and the next candidate would
    be talking into the previous conversation."""
    model = StubModel(reset_error=RuntimeError("the device is unhappy"))
    server = a_server(model)
    serve(server, FakeWS(a_call(), until=lambda: model.steps >= 3))
    assert model.closed, "released rather than reused in an unknown state"

    ws = serve(server, FakeWS(a_call()))
    assert ws.closed_with is not None and ws.closed_with[0] == p.CLOSE_BUSY
    assert not ws.sent, "nothing was served on the refused connection"
