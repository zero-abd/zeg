"""The client's real connection, against a stand-in for the websocket library.

The library is not a dependency of this package's tests, and the link was untested for
that reason. A stand-in is enough to exercise what is ours: the thread, the send queue,
the flush on close and the close itself. The wire is not exercised.
"""

import asyncio
import json
import sys
import time
import types

import pytest

from zeg.backends.gb10 import WebSocketLink
from zeg.runtime import protocol as p


class FakeServerConnection:
    """Records what reached the runtime; ends iteration when either side closes."""

    def __init__(self):
        self.received = []
        self.closed_cleanly = False
        self._incoming = None

    def _queue(self):
        if self._incoming is None:
            self._incoming = asyncio.Queue()
        return self._incoming

    async def send(self, raw):
        await asyncio.sleep(0.01)  # a real send takes a moment
        self.received.append(json.loads(raw)["type"])

    def __aiter__(self):
        return self

    async def __anext__(self):
        item = await self._queue().get()
        if item is None:
            raise StopAsyncIteration
        return item

    async def close(self):
        self.closed_cleanly = True
        await self._queue().put(None)


class _Connect:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return None


@pytest.fixture
def server(monkeypatch):
    conn = FakeServerConnection()
    fake = types.SimpleNamespace(connect=lambda url, **kwargs: _Connect(conn))
    monkeypatch.setitem(sys.modules, "websockets", fake)
    return conn


def test_messages_queued_before_close_reach_the_runtime(server):
    """Three audio frames and the session's final stop, queued just before close, never
    left: close stopped the event loop outright."""
    link = WebSocketLink("ws://runtime")
    wire = p.Wire("client")
    for _ in range(3):
        link.send(wire.audio(b"\x00" * p.INPUT_FRAME_BYTES))
    link.send(wire.stop())
    link.close()

    assert server.received == [p.AUDIO, p.AUDIO, p.AUDIO, p.STOP]


def test_the_connection_is_closed_not_abandoned(server):
    link = WebSocketLink("ws://runtime")
    link.close()
    assert server.closed_cleanly


def test_close_waits_for_the_connection_to_end(server):
    """A rollover opens the next connection straight after closing this one, on a runtime
    that serves one conversation at a time. close returned before anything had closed."""
    link = WebSocketLink("ws://runtime")
    link.send(p.Wire("client").stop())
    link.close()
    assert not link._thread.is_alive(), "close returned while the connection was still open"
    assert link.closed


def test_nothing_is_sent_after_close(server):
    link = WebSocketLink("ws://runtime")
    link.close()
    link.send(p.Wire("client").stop())
    time.sleep(0.05)
    assert p.STOP not in server.received


def test_close_is_idempotent(server):
    link = WebSocketLink("ws://runtime")
    link.close()
    link.close()
    assert link.closed


def test_a_connection_the_runtime_ends_marks_the_link_closed(server):
    link = WebSocketLink("ws://runtime")
    loop = link._loop
    asyncio.run_coroutine_threadsafe(server.close(), loop).result(timeout=1)
    link._thread.join(timeout=1)
    assert link.closed
