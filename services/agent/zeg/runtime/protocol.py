"""The wire protocol between the call process and the model process.

One loopback WebSocket, one session per connection, JSON text frames both ways.
Audio rides base64 inside the JSON rather than as binary frames: on loopback the
33% is free, and a single ordered stream removes the correlation problem between
two framings. Ordering is what is hard to debug here. Bytes are not.

This module is pure stdlib and is shared by both sides. That is deliberate. A
protocol defined twice is a protocol that drifts, and the first symptom of drift
is a candidate hearing silence.

Nothing here decides anything. Lifecycle rules live in `session.py` on the server
side and in `backends/gb10.py` on the client side; this file only builds, parses
and validates messages.
"""

import base64
import binascii
import json
from typing import Any, Dict, List, Optional

PROTOCOL_NAME = "zeg.voice"
PROTOCOL_VERSION = 1

# --- The frame clock ---------------------------------------------------------

#: One model step. Every rate in the model lands on this, so it is the only clock
#: the two processes agree on.
FRAME_MS = 80

INPUT_SAMPLE_RATE = 16_000
OUTPUT_SAMPLE_RATE = 22_050

#: 80 ms in, 80 ms out. Both divide exactly into four 20 ms transport frames, which
#: is why nothing has to be repacketized between this layer and RTP.
INPUT_FRAME_SAMPLES = INPUT_SAMPLE_RATE * FRAME_MS // 1000       # 1280
OUTPUT_FRAME_SAMPLES = OUTPUT_SAMPLE_RATE * FRAME_MS // 1000     # 1764

BYTES_PER_SAMPLE = 2
INPUT_FRAME_BYTES = INPUT_FRAME_SAMPLES * BYTES_PER_SAMPLE
OUTPUT_FRAME_BYTES = OUTPUT_FRAME_SAMPLES * BYTES_PER_SAMPLE

#: Hard cap on one session, in model frames. 12,000 x 80 ms is 16 minutes. Past it
#: the model's state no longer fits and the session is closed rather than degraded.
MAX_SESSION_FRAMES = 12_000

#: WebSocket close codes we use. 1000 is a normal close; 1013 says "try later",
#: which is the honest answer when a conversation is already in progress.
CLOSE_NORMAL = 1000
CLOSE_BUSY = 1013


# --- Message types -----------------------------------------------------------

# Client to server.
CONFIGURE = "session.configure"
TURN_START = "input.turn_start"
AUDIO = "input.audio"
TURN_COMMIT = "input.turn_commit"
CANCEL = "response.cancel"
STOP = "session.stop"

# Server to client.
READY = "session.ready"
CONFIGURED = "session.configured"
TURN_STARTED = "input.turn_started"
TURN_COMMITTED = "input.turn_committed"
TRANSCRIPT_DELTA = "transcript.delta"
TRANSCRIPT_FINAL = "transcript.final"
RESPONSE_STARTED = "response.started"
RESPONSE_TEXT = "response.text"
RESPONSE_AUDIO = "response.audio"
RESPONSE_CANCELLED = "response.cancelled"
RESPONSE_DONE = "response.done"
PROGRESS = "session.progress"
ERROR = "error"
CLOSED = "session.closed"


class ProtocolError(ValueError):
    """A message violates the contract.

    Raised on malformed input on either side. Whether it is fatal is a lifecycle
    decision, not a parsing one, so it is not encoded here.
    """


# --- Building ----------------------------------------------------------------


class Wire:
    """Builds messages with monotonic, prefixed event IDs.

    IDs are sequential rather than random so a trace reads in order and a test can
    assert on them. The prefix separates the two directions in a merged log, which
    is the only place you can see an ordering bug.
    """

    def __init__(self, prefix: str = "c") -> None:
        self.prefix = prefix
        self._n = 0

    def _msg(self, type_: str, **fields: Any) -> Dict[str, Any]:
        self._n += 1
        msg = {"type": type_, "event_id": "%s_%d" % (self.prefix, self._n)}
        msg.update(fields)
        return msg

    # --- client to server -----------------------------------------------------

    def configure(
        self,
        instructions: Optional[str],
        greeting: Optional[str] = None,
        max_session_frames: int = MAX_SESSION_FRAMES,
    ) -> Dict[str, Any]:
        """The one pre-audio message. No audio may be sent before it is answered."""
        return self._msg(
            CONFIGURE,
            session={
                "protocol_version": PROTOCOL_VERSION,
                "instructions": instructions,
                "greeting": greeting,
                "max_session_frames": max_session_frames,
            },
        )

    def turn_start(self, turn: int, preroll_frames: int = 0) -> Dict[str, Any]:
        """Open turn `turn`.

        `preroll_frames` tells the server how many of the frames that follow were
        captured before the voice gate tripped. The gate is always late; without
        the pre-roll the model loses the first syllable and confabulates it back.
        """
        if turn < 1:
            raise ProtocolError("turn numbers start at 1")
        return self._msg(TURN_START, turn=turn, preroll_frames=preroll_frames)

    def audio(self, pcm: bytes) -> Dict[str, Any]:
        """One 80 ms frame of caller audio."""
        if len(pcm) != INPUT_FRAME_BYTES:
            raise ProtocolError(
                "input frame must be %d bytes, got %d" % (INPUT_FRAME_BYTES, len(pcm))
            )
        return self._msg(
            AUDIO,
            encoding="pcm16",
            sample_rate=INPUT_SAMPLE_RATE,
            channels=1,
            audio=base64.b64encode(pcm).decode("ascii"),
        )

    def turn_commit(self, turn: int) -> Dict[str, Any]:
        """Close turn `turn` and request exactly one response.

        Authoritative even if the recognizer decoded nothing. A commit is a request
        for one turn transition, not a hint.
        """
        if turn < 1:
            raise ProtocolError("turn numbers start at 1")
        return self._msg(TURN_COMMIT, turn=turn)

    def cancel(self, reason: str = "barge_in") -> Dict[str, Any]:
        return self._msg(CANCEL, reason=reason)

    def stop(self) -> Dict[str, Any]:
        return self._msg(STOP)

    # --- server to client -----------------------------------------------------

    def ready(self, session_id: str, limits: Dict[str, Any]) -> Dict[str, Any]:
        return self._msg(
            READY,
            protocol={"name": PROTOCOL_NAME, "version": PROTOCOL_VERSION},
            session={"id": session_id},
            limits=limits,
        )

    def configured(self, session_id: str, limits: Dict[str, Any]) -> Dict[str, Any]:
        """The model-ready barrier.

        Sent only once the system prompt is prefilled into the model. The client
        does not send audio before this, and audio captured while waiting for it is
        discarded rather than buffered: replaying stale audio into a model that is
        now listening answers a question the candidate has already moved on from.
        """
        return self._msg(
            CONFIGURED,
            protocol={"name": PROTOCOL_NAME, "version": PROTOCOL_VERSION},
            session={"id": session_id},
            limits=limits,
        )

    def turn_started(self, turn: int, turn_id: str) -> Dict[str, Any]:
        return self._msg(TURN_STARTED, turn=turn, turn_id=turn_id)

    def turn_committed(self, turn: int, turn_id: str) -> Dict[str, Any]:
        return self._msg(TURN_COMMITTED, turn=turn, turn_id=turn_id)

    def transcript_delta(self, turn_id: str, delta: str, text: str) -> Dict[str, Any]:
        return self._msg(TRANSCRIPT_DELTA, turn_id=turn_id, delta=delta, text=text)

    def transcript_final(self, turn_id: str, text: str) -> Dict[str, Any]:
        return self._msg(TRANSCRIPT_FINAL, turn_id=turn_id, text=text)

    def response_started(self, response_id: str, turn_id: Optional[str]) -> Dict[str, Any]:
        return self._msg(RESPONSE_STARTED, response_id=response_id, turn_id=turn_id)

    def response_text(self, response_id: str, delta: str, text: str) -> Dict[str, Any]:
        return self._msg(RESPONSE_TEXT, response_id=response_id, delta=delta, text=text)

    def response_audio(self, response_id: str, pcm: bytes, frame: int) -> Dict[str, Any]:
        if len(pcm) != OUTPUT_FRAME_BYTES:
            raise ProtocolError(
                "output frame must be %d bytes, got %d" % (OUTPUT_FRAME_BYTES, len(pcm))
            )
        return self._msg(
            RESPONSE_AUDIO,
            response_id=response_id,
            encoding="pcm16",
            sample_rate=OUTPUT_SAMPLE_RATE,
            channels=1,
            frame=frame,
            audio=base64.b64encode(pcm).decode("ascii"),
        )

    def response_cancelled(self, response_id: str, reason: str) -> Dict[str, Any]:
        return self._msg(RESPONSE_CANCELLED, response_id=response_id, reason=reason)

    def response_done(self, response_id: str, status: str, reason: str) -> Dict[str, Any]:
        if status not in ("completed", "cancelled", "failed"):
            raise ProtocolError("unknown response status: %r" % status)
        return self._msg(RESPONSE_DONE, response_id=response_id, status=status, reason=reason)

    def progress(self, frames: int, remaining: int, over_budget: int) -> Dict[str, Any]:
        """Liveness and budget in one message.

        Transport keepalive is disabled on purpose, because a slow model step must
        not be killed by a ping timeout. What the client actually needs to know is
        whether frames are still being produced, and that is this.
        """
        return self._msg(PROGRESS, frames=frames, remaining=remaining, over_budget=over_budget)

    def error(self, code: str, message: str, fatal: bool = False) -> Dict[str, Any]:
        return self._msg(ERROR, error={"code": code, "message": message, "fatal": fatal})

    def closed(self, reason: str, status: str = "completed") -> Dict[str, Any]:
        return self._msg(CLOSED, reason=reason, status=status)


# --- Parsing -----------------------------------------------------------------


def dumps(msg: Dict[str, Any]) -> str:
    return json.dumps(msg, separators=(",", ":"))


def parse(raw: Any) -> Dict[str, Any]:
    """Parse one message off the socket.

    Binary frames are refused rather than guessed at. There is exactly one framing
    on this socket and accepting a second one quietly is how a protocol grows a
    second, undocumented protocol.
    """
    if isinstance(raw, (bytes, bytearray)):
        raise ProtocolError("messages must be JSON text, not binary frames")
    try:
        msg = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ProtocolError("invalid JSON: %s" % exc)
    if not isinstance(msg, dict):
        raise ProtocolError("a message must be a JSON object")
    if not isinstance(msg.get("type"), str):
        raise ProtocolError("a message needs a string type")
    return msg


def _decode_audio(msg: Dict[str, Any], sample_rate: int, expect_bytes: int) -> bytes:
    if msg.get("encoding") != "pcm16":
        raise ProtocolError("audio encoding must be pcm16")
    if msg.get("sample_rate") != sample_rate:
        raise ProtocolError("audio must be at %d Hz" % sample_rate)
    if msg.get("channels") != 1:
        raise ProtocolError("audio must be mono")
    payload = msg.get("audio")
    if not isinstance(payload, str):
        raise ProtocolError("audio payload must be base64 text")
    try:
        pcm = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ProtocolError("audio payload is not valid base64: %s" % exc)
    if len(pcm) != expect_bytes:
        raise ProtocolError("audio frame must be %d bytes, got %d" % (expect_bytes, len(pcm)))
    return pcm


def decode_input_audio(msg: Dict[str, Any]) -> bytes:
    """Decode one caller frame. 16 kHz mono, exactly 80 ms."""
    return _decode_audio(msg, INPUT_SAMPLE_RATE, INPUT_FRAME_BYTES)


def decode_output_audio(msg: Dict[str, Any]) -> bytes:
    """Decode one agent frame. 22.05 kHz mono, exactly 80 ms."""
    return _decode_audio(msg, OUTPUT_SAMPLE_RATE, OUTPUT_FRAME_BYTES)


def check_version(msg: Dict[str, Any]) -> None:
    """Fail the handshake loudly on a version mismatch.

    There is no compatibility mode and there is not going to be one. Two processes
    on the same box are deployed together; a version skew here means someone
    restarted half the stack, and saying so beats negotiating around it.
    """
    protocol = msg.get("protocol") or {}
    if protocol.get("name") != PROTOCOL_NAME:
        raise ProtocolError("unknown protocol: %r" % (protocol.get("name"),))
    if protocol.get("version") != PROTOCOL_VERSION:
        raise ProtocolError(
            "protocol version %r, expected %d" % (protocol.get("version"), PROTOCOL_VERSION)
        )


def split_output_frame(pcm: bytes, parts: int = 4) -> List[bytes]:
    """Split one 80 ms model frame into `parts` equal transport frames.

    4 x 441 samples at 22.05 kHz is exactly 1764, so this is lossless and drift-free
    over a whole call. Anything that does not divide evenly is a bug in the caller,
    not something to round.
    """
    if parts < 1:
        raise ProtocolError("parts must be positive")
    if len(pcm) % (parts * BYTES_PER_SAMPLE):
        raise ProtocolError("frame of %d bytes does not split into %d parts" % (len(pcm), parts))
    size = len(pcm) // parts
    return [pcm[i * size:(i + 1) * size] for i in range(parts)]
