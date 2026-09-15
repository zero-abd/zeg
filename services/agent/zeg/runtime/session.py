"""Server-side session lifecycle.

One class, one call, no model. Everything here is a pure state machine over the
protocol in `protocol.py`: it decides when a turn is open, when a response is
open, when to give up on a response that has stopped making progress, and when
the session has run out of frames.

It is pure on purpose. The parts of a realtime voice server that actually break
are lifecycle parts — a response that never terminates, two turns open at once, a
cancel that arrives after the thing it cancels — and none of them need a GPU to
reproduce. Model work happens in `loop.py` and reaches this file as `FrameResult`.

The division this file enforces, from docs/11-runtime.md: the client owns turn
boundaries, the server owns continuous model state.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from . import protocol as p

#: A response that has produced no text and no audible audio for this many frames
#: has stalled. 30 frames is 2.4 s, which is longer than any natural gap inside a
#: sentence and shorter than a candidate's patience.
NO_PROGRESS_FRAMES = 30

#: After something audible has been heard, this many silent frames means the
#: response is acoustically over even if the model has not said so. 12 frames is
#: just under a second.
TRAILING_SILENCE_FRAMES = 12

#: How often to send a progress message. Every 25 frames is every 2 s, which is
#: well inside the client's watchdog window and cheap enough to ignore.
PROGRESS_EVERY = 25


@dataclass
class FrameResult:
    """What one model step produced.

    `audible` is separate from `audio_pcm` because the model emits a frame every
    step whether or not it is speaking: silence is data, and "produced a frame" is
    not the same claim as "said something".
    """

    text_delta: str = ""
    audio_pcm: bytes = b""
    user_text: str = ""
    control: Optional[str] = None  # "response_open" | "response_close"
    audible: bool = False
    over_budget: bool = False


@dataclass
class Action:
    """Something the session wants the model loop to do.

    Returned rather than called so this file stays synchronous and testable. The
    server drains these after every client message.
    """

    kind: str  # "audio" | "commit" | "cancel" | "close" | "say" | "steer"
    payload: Any = None


class ResponseWatchdog:
    """Ends a response that has opened and then stopped making progress.

    Three separate stalls, because they have three separate causes and collapsing
    them loses the diagnosis: the model emitting nothing at all, the model still
    emitting text while the synthesis decoder has gone quiet, and a response that
    was audible and has now been silent long enough to be over.

    Every outcome is "close this response cleanly". None of them is "say something
    to fill the gap" — a voice agent that invents filler when it is confused is
    worse than one that stops.
    """

    def __init__(
        self,
        no_progress_frames: int = NO_PROGRESS_FRAMES,
        trailing_silence_frames: int = TRAILING_SILENCE_FRAMES,
    ) -> None:
        self.no_progress_frames = no_progress_frames
        self.trailing_silence_frames = trailing_silence_frames
        self.reset()

    def reset(self) -> None:
        self.open = False
        self.heard_audio = False
        self.idle_frames = 0
        self.silent_frames = 0
        self.fired = False

    def observe(self, result: FrameResult) -> Optional[str]:
        """Return a reason to close the response, or None. Fires at most once."""
        if result.control == "response_open":
            self.reset()
            self.open = True
        if not self.open:
            return None

        progress = bool(result.text_delta) or result.audible
        self.idle_frames = 0 if progress else self.idle_frames + 1

        if result.audible:
            self.heard_audio = True
            self.silent_frames = 0
        elif self.heard_audio:
            self.silent_frames += 1

        if result.control == "response_close":
            self.reset()
            return None

        if self.fired:
            return None
        if self.idle_frames >= self.no_progress_frames:
            self.fired = True
            return "no_progress"
        if self.heard_audio and self.silent_frames >= self.trailing_silence_frames:
            self.fired = True
            return "trailing_silence"
        return None


class ServerSession:
    """One conversation, from handshake to close.

    Not reusable. The model behind it is stateful and single-tenant, so a session
    and a connection are the same lifetime by construction.
    """

    def __init__(
        self,
        session_id: str,
        max_session_frames: int = p.MAX_SESSION_FRAMES,
        watchdog: Optional[ResponseWatchdog] = None,
    ) -> None:
        self.session_id = session_id
        self.max_session_frames = max_session_frames
        self.wire = p.Wire(prefix=session_id)
        self.watchdog = watchdog or ResponseWatchdog()
        self.actions: List[Action] = []

        self.configured = False
        self.closed = False
        self.instructions: Optional[str] = None
        self.greeting: Optional[str] = None

        self.frames = 0
        self.over_budget = 0

        self._turn: Optional[int] = None
        self._turn_id: Optional[str] = None
        self._turn_index = 0
        self._turn_text = ""
        self._turn_text_sent = 0

        self._response_id: Optional[str] = None
        self._response_index = 0
        self._response_text = ""
        self._response_turn_id: Optional[str] = None
        self._cancel_reason: Optional[str] = None

    # --- limits advertised in the handshake -----------------------------------

    @property
    def limits(self) -> Dict[str, Any]:
        return {
            "max_session_frames": self.max_session_frames,
            "frame_ms": p.FRAME_MS,
            "input_sample_rate": p.INPUT_SAMPLE_RATE,
            "output_sample_rate": p.OUTPUT_SAMPLE_RATE,
            "single_session": True,
            "client_owns_turns": True,
        }

    def ready(self) -> Dict[str, Any]:
        return self.wire.ready(self.session_id, self.limits)

    # --- client messages ------------------------------------------------------

    def on_client(self, msg: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle one client message. Returns what to send back.

        Anything that would leave the model in a half-mutated state is fatal rather
        than recoverable: a partially transmitted turn has already been consumed
        into the model's recurrent state and there is no undo.
        """
        if self.closed:
            return []
        kind = msg.get("type")

        if kind == p.CONFIGURE:
            return self._configure(msg)
        if not self.configured:
            return self._fatal("not_configured", "audio before the session was configured")

        if kind == p.AUDIO:
            return self._audio(msg)
        if kind == p.TURN_START:
            return self._turn_start(msg)
        if kind == p.TURN_COMMIT:
            return self._turn_commit(msg)
        if kind == p.CANCEL:
            return self._cancel(msg.get("reason") or "barge_in")
        if kind == p.SAY:
            return self._say(msg)
        if kind == p.STEER:
            return self._steer(msg)
        if kind == p.STOP:
            return self.close("client_stop")
        return [self.wire.error("unknown_message", "unknown message type: %r" % kind)]

    def _say(self, msg: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Speak exact text.

        Rejected mid-turn. A turn is open means the candidate is still talking, and
        speaking over them is the failure they will remember. The client is expected to
        do this at a turn boundary; if it does not, that is a client bug worth naming
        rather than papering over.
        """
        text = msg.get("text")
        if not isinstance(text, str) or not text.strip():
            return [self.wire.error("bad_say", "say needs non-empty text")]
        if self._turn_id is not None:
            return [self.wire.error("say_mid_turn", "say is only valid at a turn boundary")]
        # An action, like every other message that needs the model. It was stored as
        # state instead, and nothing ever came to collect it: the disclosure reached
        # the server and went no further.
        self.actions.append(Action("say", text))
        return []

    def _steer(self, msg: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Context guidance for the model. Never spoken.

        This is the path every briefing and every rollover seed takes, so a steer that
        is accepted and then dropped is the memory layer silently switched off.
        """
        text = msg.get("text")
        if not isinstance(text, str) or not text.strip():
            return [self.wire.error("bad_steer", "steer needs non-empty text")]
        self.actions.append(Action("steer", text))
        return []

    def _configure(self, msg: Dict[str, Any]) -> List[Dict[str, Any]]:
        if self.configured:
            # Settings lock once the session is live. Re-prompting a model that is
            # already holding recurrent state does not do what it looks like it does.
            return [self.wire.error("already_configured", "settings are locked")]
        session = msg.get("session") or {}
        version = session.get("protocol_version")
        if version != p.PROTOCOL_VERSION:
            return self._fatal(
                "protocol_version",
                "client speaks version %r, this server speaks %d"
                % (version, p.PROTOCOL_VERSION),
            )
        self.instructions = session.get("instructions")
        self.greeting = session.get("greeting")
        requested = session.get("max_session_frames")
        if isinstance(requested, int) and 0 < requested < self.max_session_frames:
            self.max_session_frames = requested
        self.configured = True
        # The caller sends this only after the prompt is prefilled: it is a barrier,
        # not an acknowledgement. See protocol.Wire.configured.
        return [self.wire.configured(self.session_id, self.limits)]

    def _audio(self, msg: Dict[str, Any]) -> List[Dict[str, Any]]:
        try:
            pcm = p.decode_input_audio(msg)
        except p.ProtocolError as exc:
            return [self.wire.error("bad_audio", str(exc))]
        # Audio flows whether or not a turn is open. The model is duplex: it hears
        # the caller on every frame, which is what makes barge-in possible at all.
        self.actions.append(Action("audio", pcm))
        return []

    def _turn_start(self, msg: Dict[str, Any]) -> List[Dict[str, Any]]:
        turn = msg.get("turn")
        if not isinstance(turn, int) or turn < 1:
            return self._fatal("bad_turn", "turn numbers are positive integers")
        if self._turn is not None:
            if self._turn == turn:
                return [self.wire.turn_started(turn, self._turn_id or "")]  # idempotent retry
            return self._fatal(
                "overlapping_turn",
                "turn %d started while turn %d is open" % (turn, self._turn),
            )
        out: List[Dict[str, Any]] = []
        if self._response_id is not None:
            # One response per turn, always terminated. A response left open while a
            # new turn starts is a model that thinks it is still mid-sentence.
            out.extend(self._cancel("superseded"))
        self._turn_index += 1
        self._turn = turn
        self._turn_id = "turn_%s_%d" % (self.session_id, self._turn_index)
        self._turn_text = ""
        self._turn_text_sent = 0
        out.append(self.wire.turn_started(turn, self._turn_id))
        return out

    def _turn_commit(self, msg: Dict[str, Any]) -> List[Dict[str, Any]]:
        turn = msg.get("turn")
        if self._turn is None or turn != self._turn:
            return self._fatal(
                "turn_mismatch",
                "commit for turn %r, open turn is %r" % (turn, self._turn),
            )
        turn_id = self._turn_id or ""
        out = [self.wire.turn_committed(turn, turn_id)]
        out.extend(self._finish_turn())
        # Authoritative even if the recognizer decoded nothing: one commit, one
        # turn transition. The loop settles the model and opens the response.
        self.actions.append(Action("commit", turn_id))
        return out

    def _finish_turn(self) -> List[Dict[str, Any]]:
        if self._turn is None:
            return []
        out = [self.wire.transcript_final(self._turn_id or "", self._turn_text)]
        self._turn = None
        self._turn_id = None
        return out

    def _cancel(self, reason: str) -> List[Dict[str, Any]]:
        if self._response_id is None:
            return []
        response_id = self._response_id
        self._cancel_reason = reason
        self.actions.append(Action("cancel", reason))
        out = [self.wire.response_cancelled(response_id, reason)]
        out.extend(self._close_response("cancelled", reason))
        return out

    # --- model frames ---------------------------------------------------------

    def on_frame(self, result: FrameResult) -> List[Dict[str, Any]]:
        """Translate one model step into protocol messages."""
        if self.closed:
            return []
        self.frames += 1
        if result.over_budget:
            self.over_budget += 1

        out: List[Dict[str, Any]] = []

        if result.control == "response_open" and self._response_id is None:
            out.append(self._open_response())
        if result.user_text and result.user_text != self._turn_text:
            out.extend(self._transcript(result.user_text))
        if result.text_delta and self._response_id is not None:
            self._response_text += result.text_delta
            out.append(
                self.wire.response_text(self._response_id, result.text_delta, self._response_text)
            )
        if result.audio_pcm and self._response_id is not None:
            out.append(self.wire.response_audio(self._response_id, result.audio_pcm, self.frames))

        stall = self.watchdog.observe(result)
        if result.control == "response_close":
            out.extend(self._close_response("completed", "model_turn_end"))
        elif stall is not None:
            # The model is not going to finish this on its own. Close it and tell
            # the loop, rather than leaving the candidate on a live but silent line.
            self.actions.append(Action("cancel", stall))
            out.extend(self._close_response("failed", stall))

        if self.frames % PROGRESS_EVERY == 0:
            out.append(
                self.wire.progress(
                    self.frames, max(0, self.max_session_frames - self.frames), self.over_budget
                )
            )
        if self.frames >= self.max_session_frames:
            out.extend(self.close("session_frame_cap"))
        return out

    def _open_response(self) -> Dict[str, Any]:
        self._response_index += 1
        self._response_id = "resp_%s_%d" % (self.session_id, self._response_index)
        self._response_turn_id = self._turn_id
        self._response_text = ""
        self._cancel_reason = None
        return self.wire.response_started(self._response_id, self._response_turn_id)

    def _close_response(self, status: str, reason: str) -> List[Dict[str, Any]]:
        if self._response_id is None:
            return []
        out = [self.wire.response_done(self._response_id, status, reason)]
        self._response_id = None
        self._response_turn_id = None
        self._response_text = ""
        self._cancel_reason = None
        self.watchdog.reset()
        return out

    def _transcript(self, text: str) -> List[Dict[str, Any]]:
        if self._turn_id is None:
            # Recognizer output outside a turn is real but unattributed. Dropping it
            # is right: the record is turn-scoped, and a floating fragment in the
            # transcript is worse than a missing one.
            return []
        delta = text[self._turn_text_sent:] if text.startswith(self._turn_text) else text
        self._turn_text = text
        self._turn_text_sent = len(text)
        if not delta:
            return []
        return [self.wire.transcript_delta(self._turn_id, delta, text)]

    # --- closing --------------------------------------------------------------

    def close(self, reason: str, status: str = "completed") -> List[Dict[str, Any]]:
        """Close every open bracket, then the session. Safe to call twice."""
        if self.closed:
            return []
        out: List[Dict[str, Any]] = []
        out.extend(self._finish_turn())
        out.extend(self._close_response("cancelled", reason))
        self.closed = True
        self.actions.append(Action("close", reason))
        out.append(self.wire.closed(reason, status=status))
        return out

    def _fatal(self, code: str, message: str) -> List[Dict[str, Any]]:
        out = [self.wire.error(code, message, fatal=True)]
        out.extend(self.close(code, status="failed"))
        return out

    def drain_actions(self) -> List[Action]:
        actions, self.actions = self.actions, []
        return actions
