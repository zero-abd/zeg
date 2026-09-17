"""The real backend: a session against the speech runtime on the GB10 box.

Same contract as the mock, same observable behaviour, a model behind it instead of
a script. The model lives in another process on the same box and this file talks
to it over a loopback WebSocket. See docs/11-runtime.md for why the split exists
and what the wire protocol is.

Three things this file owns, and they are the three things that make a voice agent
feel alive or dead:

**Turn boundaries.** The model has its own endpointer and we do not use it. Its
threshold is tuned for natural conversational pauses, which in an interview is the
exact moment a candidate is thinking. Endpointing is an interview design decision,
so it lives here, where it can be tuned per role, and the runtime is told where the
boundaries are with explicit barriers.

**Barge-in, immediately.** When the caller talks over the agent, playback stops
here and now. The cancel also goes to the model, because it has to close its
response properly, but nothing waits for that round trip.

**Failing safe.** A watchdog ends the call cleanly rather than leaving a candidate
on a live, silent line. It counts caller frames rather than wall-clock seconds —
caller audio arrives in real time by definition, so counting it is counting real
elapsed call time, and it keeps the whole failure path exercisable under the
virtual clock in `conversation.py`.

Everything heavy is imported lazily. Importing this module on a laptop with no GPU
and no WebSocket library works; opening a session does not.
"""

import collections
import math
import threading
from dataclasses import dataclass
from typing import Any, Deque, Dict, Iterator, List, Optional

from ..audio import AudioFrame, rms
from ..config import AudioConfig, BackendConfig
from ..hesitation import is_hesitation, sounds_unfinished
from ..runtime import protocol as p
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


@dataclass
class GB10Config:
    """Tuning for the call side. Every default here is a starting point.

    None of these numbers has been validated against a real candidate on real
    hardware, and the two that matter most — the speech threshold and the
    endpoint — will need a morning with headphones on the box.
    """

    url: str = "ws://127.0.0.1:8787"

    #: Above this RMS a frame counts as speech. The same crude gate the mock uses.
    #: A real gate is a small model; this is enough to open and close turns and it
    #: has the large advantage of being free and deterministic.
    speech_rms: float = 0.02

    #: Consecutive frames above the threshold before the gate believes it is speech.
    #: Three frames is 60 ms. A cough, a door or a keyboard is one or two loud frames
    #: and used to cut the agent off mid-sentence; a person starting to talk is loud
    #: for far longer than this. The cost is 60 ms of extra barge-in latency, which is
    #: invisible next to being interrupted by a dog.
    min_speech_frames: int = 3

    #: Silence after speech before we call the turn over. Longer than a breath,
    #: shorter than a thought. 640 ms is a compromise and should be tuned per role:
    #: a systems question earns longer pauses than a behavioural one.
    endpoint_silence_ms: int = 640

    #: Silence before committing a turn that so far holds only a hesitation. "um" and a
    #: pause is someone thinking, and committing it made the model answer them mid-
    #: thought. Still finite, so a candidate who says "um" and nothing else does not hold
    #: the line open. Like the endpoint above, the number wants tuning on the box.
    hesitation_hold_ms: int = 2000

    #: How many already-sent model frames to mark as part of a turn when it opens.
    #: The gate always fires after speech has started, so without this the model
    #: loses the first syllable and confabulates it back.
    max_preroll_frames: int = 4

    #: Caller frames with no message at all from the runtime before we give up.
    #: 200 frames is 4 s. The runtime sends progress every 2 s, so silence this
    #: long means it is wedged, not busy.
    watchdog_frames: int = 200

    #: How long a fixed line that has been sent counts as the agent speaking before the
    #: runtime starts it. 150 frames is 3 s, far past a prefill of one sentence. Bounded
    #: so a line the runtime lost cannot hold off a rollover for the rest of the call.
    say_start_frames: int = 150

    #: Hard session limit, in model frames. 16 minutes. The interview wall clock in
    #: CallConfig ends the call 90 seconds before this, so reaching it means the
    #: layer above failed, which is why it is reported as an error.
    max_session_frames: int = p.MAX_SESSION_FRAMES

    connect_timeout_s: float = 10.0


# --- Transport ---------------------------------------------------------------


class Link:
    """What a session needs from a connection. Four methods, all non-blocking.

    Kept this small so tests can supply a fake one and exercise the entire session
    — turn barriers, barge-in, the watchdog, the frame cap — with no socket, no
    event loop and no timing.
    """

    def send(self, msg: Dict[str, Any]) -> None:
        raise NotImplementedError

    def drain(self) -> List[Dict[str, Any]]:
        """Return whatever arrived since the last call. Never blocks."""
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    @property
    def closed(self) -> bool:
        raise NotImplementedError


class WebSocketLink(Link):
    """A real connection, on its own thread with its own event loop.

    The backend contract is synchronous: `push_audio` must not block and `poll`
    must return immediately. An asyncio client behind a thread is the smallest
    thing that satisfies that without making every caller async.

    Tested against a stand-in for the websocket library, not a live runtime: the thread,
    the queue, the flush and the close are exercised, the wire itself is not.
    """

    #: How long `close` waits for queued messages to go out and the connection to end.
    close_timeout_s = 2.0

    def __init__(self, url: str, connect_timeout_s: float = 10.0) -> None:
        self.url = url
        self._inbox: Deque[Dict[str, Any]] = collections.deque()
        self._ready = threading.Event()
        self._closed = threading.Event()
        self._error: Optional[BaseException] = None
        self._loop: Any = None
        self._outbox: Any = None
        self._ws: Any = None
        self._main_task: Any = None
        self._thread = threading.Thread(target=self._run, name="zeg-link", daemon=True)
        self._thread.start()
        if not self._ready.wait(connect_timeout_s):
            self.close()
            raise RuntimeError(
                "no speech runtime at %s after %gs. Start it with "
                "`python -m zeg.runtime` on the box." % (url, connect_timeout_s)
            )
        if self._error is not None:
            raise RuntimeError("could not reach the speech runtime: %s" % self._error)

    def _run(self) -> None:
        import asyncio  # noqa: WPS433 - deliberate lazy import

        try:
            import websockets  # noqa: WPS433 - deliberate lazy import
        except ImportError as exc:
            self._error = exc
            self._ready.set()
            return

        async def main() -> None:
            self._loop = asyncio.get_event_loop()
            self._main_task = asyncio.current_task()
            self._outbox = asyncio.Queue()
            # Keepalive off: a long model step is not a dead connection, and a ping
            # timeout that kills a session mid-answer is worse than no ping at all.
            async with websockets.connect(
                self.url, ping_interval=None, ping_timeout=None
            ) as ws:
                self._ws = ws
                self._ready.set()
                sender = asyncio.ensure_future(self._sender(ws))
                try:
                    async for raw in ws:
                        try:
                            self._inbox.append(p.parse(raw))
                        except p.ProtocolError as exc:
                            self._inbox.append(
                                {
                                    "type": p.ERROR,
                                    "error": {
                                        "code": "bad_message",
                                        "message": str(exc),
                                        "fatal": True,
                                    },
                                }
                            )
                finally:
                    sender.cancel()

        try:
            asyncio.run(main())
        except BaseException as exc:  # noqa: B902 - reported, not swallowed
            self._error = exc
        finally:
            self._ready.set()
            self._closed.set()

    async def _sender(self, ws: Any) -> None:
        while True:
            msg = await self._outbox.get()
            try:
                await ws.send(p.dumps(msg))
            finally:
                # Counted either way, so a close waiting for the queue to empty is not
                # held up by a send that failed.
                self._outbox.task_done()

    async def _close_gracefully(self) -> None:
        import asyncio  # noqa: WPS433 - deliberate lazy import

        try:
            await asyncio.wait_for(self._outbox.join(), timeout=1.0)
        except asyncio.TimeoutError:
            pass
        if self._ws is not None:
            await self._ws.close()

    def send(self, msg: Dict[str, Any]) -> None:
        if self._closed.is_set() or self._loop is None or self._outbox is None:
            return
        self._loop.call_soon_threadsafe(self._outbox.put_nowait, msg)

    def drain(self) -> List[Dict[str, Any]]:
        out = []
        while self._inbox:
            out.append(self._inbox.popleft())
        return out

    def close(self) -> None:
        """Send what is queued, close the connection properly, and wait for it to end.

        It stopped the event loop outright. Measured against a stand-in library: three
        audio frames and the session's final stop, queued just before, never left; the
        connection was abandoned rather than closed; and close returned at once, so a
        rollover opened the next connection while this one was still open, on a runtime
        that serves one conversation at a time.
        """
        import asyncio  # noqa: WPS433 - deliberate lazy import

        if self._closed.is_set():
            return
        self._closed.set()
        loop = self._loop
        if loop is None or not self._thread.is_alive():
            return
        try:
            if self._ws is None and self._main_task is not None:
                # Never connected: cancel the attempt. Waiting for a graceful close held a
                # connect timeout up by two more seconds, and the attempt kept running. If
                # the runtime came up a moment later it could still connect, and take the
                # one conversation the runtime serves from every real caller after it.
                loop.call_soon_threadsafe(self._main_task.cancel)
            else:
                asyncio.run_coroutine_threadsafe(self._close_gracefully(), loop)
        except RuntimeError:
            return  # the loop has already finished on its own
        self._thread.join(timeout=self.close_timeout_s)

    @property
    def closed(self) -> bool:
        return self._closed.is_set()


# --- The session -------------------------------------------------------------


class GB10Session(VoiceSession):
    """One call against the speech runtime.

    Frames go in at 20 ms and are aggregated into the model's 80 ms frames on the
    way out; agent audio comes back at 80 ms and is split into 20 ms frames on the
    way in. Both divide exactly, so nothing drifts over a 15-minute call.

    Not thread-safe. One caller drives it, exactly as the contract says.
    """

    def __init__(
        self,
        link: Link,
        system_prompt: str,
        greeting: Optional[str] = None,
        audio: Optional[AudioConfig] = None,
        config: Optional[GB10Config] = None,
    ) -> None:
        self._link = link
        self._audio = audio or AudioConfig()
        self._cfg = config or GB10Config()
        self._wire = p.Wire(prefix="call")

        self._pending: Deque[BackendEvent] = collections.deque()
        self._playout: Deque[AudioFrame] = collections.deque()
        self._closed = False
        self._stopping = False

        # Handshake. No audio may be sent before the runtime answers.
        self._configured = False
        self._discarded_frames = 0

        # Caller-side turn state.
        self._turn = 0
        self._turn_open = False
        self._loud = False
        self._silence_frames = 0
        self._loud_run = 0
        self._onset_model_frame: Optional[int] = None
        #: The runtime's id for the open turn, and what it has heard in it so far. Only
        #: text carrying this id counts, because the previous turn keeps settling, and
        #: sending transcript, for a while after the next one opens.
        self._open_turn_id: Optional[str] = None
        self._open_turn_text = ""

        # Frame accounting. Transport frames are 20 ms; model frames are 80 ms.
        self._transport_buffer = b""
        self._transport_frames = 0
        self._model_frames = 0
        self._frames_since_message = 0
        self._out_clock = 0.0

        # Response state.
        self._response_id: Optional[str] = None
        #: The response whose audio is queued or playing. Outlives `_response_id`, which
        #: clears when the runtime says the response is done, while its audio still plays.
        self._playing_response_id: Optional[str] = None
        self._response_text = ""
        self._interrupted = False
        #: Fixed lines asked for while the caller's turn was open. The server refuses a
        #: say mid-turn, so they wait here and go out the moment the turn commits.
        self._deferred_says = []
        #: Fixed lines sent that the runtime has not started speaking yet, and the
        #: transport frame the latest went out on.
        self._says_unstarted = 0
        self._say_sent_frame = 0

        self._link.send(
            self._wire.configure(
                system_prompt,
                greeting=greeting,
                max_session_frames=self._cfg.max_session_frames,
            )
        )
        # The runtime usually answers within a frame or two, and anything it has
        # already said is drained here so a caller that polls first sees it.
        self._absorb()

    # --- VoiceSession ---------------------------------------------------------

    def push_audio(self, frame: AudioFrame) -> None:
        if self._closed:
            raise RuntimeError("session is closed")
        if frame.sample_rate != self._audio.input_sample_rate:
            # Resampling belongs in the media path, with a real anti-alias filter.
            # A naive upsample here would quietly degrade recognition, and a
            # transcription gap becomes a scoring gap.
            raise ValueError(
                "expected %d Hz, got %d Hz. Resample in the media gateway."
                % (self._audio.input_sample_rate, frame.sample_rate)
            )
        if frame.n_samples != self._audio.input_frame_samples:
            # Every timing on the caller side counts frames and assumes each is one
            # configured frame long: the endpoint, the barge-in threshold, the watchdog,
            # and the pacing of the agent's own audio. Measured with 10 ms frames, a turn
            # ended after 320 ms of silence against a 640 ms endpoint; with 40 ms frames,
            # after 1280 ms. Refused here so a mismatch is an error, not a quiet halving.
            raise ValueError(
                "expected %d samples (%d ms), got %d. Re-frame in the media gateway."
                % (self._audio.input_frame_samples, self._audio.frame_ms, frame.n_samples)
            )

        self._absorb()
        self._transport_frames += 1
        self._frames_since_message += 1

        if not self._configured:
            # Audio captured before the runtime is ready is discarded, never
            # buffered. Replaying stale audio into a model that is now listening
            # answers a question the candidate has already moved on from.
            self._discarded_frames += 1
            self._check_watchdog()
            return

        loud = rms(frame) >= self._cfg.speech_rms
        self._gate(loud)
        self._enqueue(frame.pcm)
        self._emit_playout()
        self._check_watchdog()

    def say(self, text: str) -> None:
        """Speak fixed text.

        Cancels any response in flight first. The caller asked for this utterance now,
        and letting a half-finished model response trail behind it is how two voices
        end up overlapping.
        """
        if self._closed:
            raise RuntimeError("session is closed")
        if self._turn_open:
            # The candidate is still talking and the server would refuse this. The
            # refusal used to arrive after the call had already closed, so nobody saw
            # it, and the transcript claimed the line was spoken. Hold it instead.
            self._deferred_says.append(text)
            return
        if self._speaking:  # a property, not a method
            # Stop the model's own reply to make room, without calling it an
            # interruption: nobody talked over the agent.
            self._stop_response("superseded", report=False)
        self._send_say(text)

    def _send_say(self, text: str) -> None:
        self._link.send(self._wire.say(text))
        self._says_unstarted += 1
        self._say_sent_frame = self._transport_frames

    def steer(self, text: str) -> None:
        """Guidance into the model's context. Never reaches the speaker."""
        if self._closed:
            raise RuntimeError("session is closed")
        self._link.send(self._wire.steer(text))

    def poll(self) -> Iterator[BackendEvent]:
        if not self._closed:
            self._absorb()
        while self._pending:
            yield self._pending.popleft()

    def close(self) -> None:
        """The caller is done. Anything still queued is discarded.

        During a rollover the runner closes this session while it is still reading
        events from it. Whatever was left queued describes speech the candidate will
        never hear, and delivering it would put those words in the transcript.
        """
        self._shutdown()
        self._pending.clear()

    def _shutdown(self) -> None:
        """End the session but keep what is queued.

        Used when the session ends itself. It queues a fatal error first, and the
        caller has to be able to poll afterwards to learn why the call died.
        """
        if self._closed:
            return
        self._closed = True
        self._stopping = True
        try:
            self._link.send(self._wire.stop())
        finally:
            self._link.close()
        self._playout.clear()
        self._deferred_says = []

    # --- caller audio ---------------------------------------------------------

    def _gate(self, loud: bool) -> None:
        """Open and close turns, and cancel the agent when the caller cuts in.

        Loudness alone is not speech. A single frame above the threshold is a cough, a
        door or a keyboard, and acting on one meant any of those stopped the agent
        mid-sentence. The gate now waits for the noise to persist, while still dating
        the onset from its first frame so the pre-roll keeps the start of the word.
        """
        if loud:
            if self._loud_run == 0 and self._onset_model_frame is None:
                self._onset_model_frame = self._model_frames
            self._loud_run += 1
            if self._loud_run < self._cfg.min_speech_frames:
                return
            if self._speaking:
                self._barge_in()
            self._silence_frames = 0
            if not self._turn_open:
                self._open_turn()
            return

        self._loud_run = 0
        if not self._turn_open:
            self._onset_model_frame = None
            return

        self._silence_frames += 1
        if self._silence_frames * self._audio.frame_ms >= self._endpoint_ms():
            self._commit_turn()

    def _endpoint_ms(self) -> int:
        """How much silence ends the open turn. Longer while all it holds is a hesitation.

        No transcript yet is not a hesitation. Holding on an empty turn would slow every
        turn whose recognition lags, which is most of them.
        """
        heard = self._open_turn_text.strip()
        # Stopping mid-thought is held the same way: "uh, let me think" and "the reason
        # was, uh" committed at the ordinary pause, and the model answered someone still
        # thinking. What is heard lags the audio, so a turn that finished on its last word
        # can still read unfinished here; the cost is the hold, once.
        if heard and (is_hesitation(heard) or sounds_unfinished(heard)):
            return max(self._cfg.endpoint_silence_ms, self._cfg.hesitation_hold_ms)
        return self._cfg.endpoint_silence_ms

    def _open_turn(self) -> None:
        self._turn += 1
        self._turn_open = True
        self._open_turn_id = None
        self._open_turn_text = ""
        preroll = 0
        if self._onset_model_frame is not None:
            preroll = min(
                self._cfg.max_preroll_frames, self._model_frames - self._onset_model_frame + 1
            )
        self._link.send(self._wire.turn_start(self._turn, preroll_frames=preroll))

    def _commit_turn(self) -> None:
        self._flush_partial()
        self._link.send(self._wire.turn_commit(self._turn))
        self._turn_open = False
        self._silence_frames = 0
        self._loud_run = 0
        self._onset_model_frame = None
        self._open_turn_id = None
        self._open_turn_text = ""
        # Lines held while the caller talked go out now, in order, after the commit so
        # the server has already seen the turn close.
        held, self._deferred_says = self._deferred_says, []
        for text in held:
            self._send_say(text)

    def _enqueue(self, pcm: bytes) -> None:
        """Aggregate 20 ms transport frames into 80 ms model frames."""
        self._transport_buffer += pcm
        while len(self._transport_buffer) >= p.INPUT_FRAME_BYTES:
            chunk = self._transport_buffer[: p.INPUT_FRAME_BYTES]
            self._transport_buffer = self._transport_buffer[p.INPUT_FRAME_BYTES:]
            self._send_model_frame(chunk)

    def _flush_partial(self) -> None:
        """Pad and send a partial frame so a commit never splits one.

        The model steps on whole frames. Committing with three quarters of a frame
        still in the buffer would either drop the end of the utterance or carry it
        into the next turn, and both of those are worse than 20 ms of padding.
        """
        if not self._transport_buffer:
            return
        pad = p.INPUT_FRAME_BYTES - len(self._transport_buffer)
        self._send_model_frame(self._transport_buffer + b"\x00" * pad)
        self._transport_buffer = b""

    def _send_model_frame(self, pcm: bytes) -> None:
        if self._model_frames >= self._cfg.max_session_frames:
            self._exhausted()
            return
        self._model_frames += 1
        self._link.send(self._wire.audio(pcm))

    # --- agent audio ----------------------------------------------------------

    @property
    def caller_speaking(self) -> bool:
        return self._turn_open

    @property
    def agent_speaking(self) -> bool:
        """Also true while a fixed line is on its way, for a bounded time.

        Between sending a line and the runtime starting it, nothing local said the agent
        was about to speak. A rollover waiting for quiet took that gap and closed the
        session, and the line was never heard: a redirect spoken over a prohibited
        question, say, leaving the candidate on silence. Not part of `_speaking`, which
        drives barge-in: nothing is playing yet, so there is nothing to interrupt.
        """
        return self._speaking or self._say_on_its_way()

    def _say_on_its_way(self) -> bool:
        return (self._says_unstarted > 0
                and self._transport_frames - self._say_sent_frame < self._cfg.say_start_frames)

    @property
    def _speaking(self) -> bool:
        return bool(self._playout) or self._response_id is not None

    def _barge_in(self) -> None:
        """The caller is talking over the agent. Stop, locally, now.

        The cancel goes to the runtime too, because the model has to close its
        response properly — its next frame depends on the token it emitted this
        frame, so an abandoned response leaves it believing it is mid-sentence.
        Nothing waits for that: a round trip plus a model step is another 80 ms of
        the agent talking over a candidate.
        """
        self._stop_response("barge_in", report=True)

    def _stop_response(self, reason: str, report: bool) -> None:
        """Stop the response in flight, locally and on the runtime.

        `report` is whether the layer above hears about it. A candidate talking over
        the agent is an interruption. The client replacing the model's own reply with a
        fixed line is not, and reporting it as one made the interview believe every
        repeat of the disclosure had been talked over, so it repeated it forever.
        """
        if self._interrupted:
            return
        self._interrupted = True
        self._playout.clear()
        if report:
            self._pending.append(AgentInterrupted())
        # Name the response whose audio the candidate is hearing. It may already be over on
        # the runtime, which has opened the next one, and an unnamed cancel stopped that.
        self._link.send(self._wire.cancel(reason, response_id=self._playing_response_id))

    def _emit_playout(self) -> None:
        """Release one 20 ms frame of agent audio per caller frame.

        Paced against the caller's clock rather than flushed on arrival. Both
        clocks are 20 ms so they match in the long run, and pacing is what leaves
        something in the queue for barge-in to cancel.
        """
        if self._playout:
            self._pending.append(AgentAudio(self._playout.popleft()))

    # --- runtime messages -----------------------------------------------------

    def _absorb(self) -> None:
        for msg in self._link.drain():
            self._frames_since_message = 0
            self._translate(msg)
        if self._link.closed and not self._closed:
            # A connection that dropped is not a runtime that went quiet. Waiting for
            # the watchdog meant four seconds of a candidate talking to nothing, and
            # the call was then reported as the runtime going silent, which sends
            # whoever reads it looking at the model rather than the connection.
            self._fail("the connection to the speech runtime closed")

    def _translate(self, msg: Dict[str, Any]) -> None:
        kind = msg.get("type")

        if kind == p.READY:
            try:
                p.check_version(msg)
            except p.ProtocolError as exc:
                self._fail(str(exc))
            return

        if kind == p.CONFIGURED:
            self._configured = True
            return

        if kind == p.TURN_STARTED:
            if self._turn_open and msg.get("turn") == self._turn:
                self._open_turn_id = msg.get("turn_id")
            return

        if kind == p.TRANSCRIPT_DELTA:
            if self._open_turn_id is not None and msg.get("turn_id") == self._open_turn_id:
                self._open_turn_text = msg.get("text") or ""
            self._pending.append(UserTranscript(msg.get("text") or "", final=False))
            return

        if kind == p.TRANSCRIPT_FINAL:
            text = msg.get("text") or ""
            if text:
                self._pending.append(UserTranscript(text, final=True))
            return

        if kind == p.RESPONSE_STARTED:
            self._response_id = msg.get("response_id")
            self._playing_response_id = self._response_id
            self._response_text = ""
            self._interrupted = False
            # The runtime does not say whether this is our line or the model's own reply.
            # Either way something is now speaking, which is all the count is for.
            self._says_unstarted = max(0, self._says_unstarted - 1)
            return

        if kind == p.RESPONSE_TEXT:
            if msg.get("response_id") != self._response_id:
                return
            delta = msg.get("delta") or ""
            self._response_text += delta
            if delta:
                self._pending.append(AgentText(delta, final=False))
            return

        if kind == p.RESPONSE_AUDIO:
            self._take_audio(msg)
            return

        if kind == p.RESPONSE_CANCELLED:
            # Either our own barge-in coming back, or the runtime's watchdog. If we
            # have not already told the caller, tell them now.
            if not self._interrupted:
                self._interrupted = True
                self._playout.clear()
                reason = msg.get("reason") or "cancelled"
                # Replaced by a fixed line is not an interruption, the same as the client
                # replacing a reply itself. Reported, it read as the candidate talking over
                # the disclosure when nobody had said a word.
                if reason != p.REPLACED_BY_FIXED_LINE:
                    self._pending.append(AgentInterrupted(reason=reason))
            return

        if kind == p.RESPONSE_DONE:
            # A final agent text is a record of what was actually spoken. A response the
            # candidate talked over, or one the client replaced with a fixed line, was
            # not spoken in full, and delivering its whole text put words in the
            # transcript the candidate never heard. That phantom line also sat between a
            # fixed line and its own echo, so the echo was recorded as a second copy.
            if self._response_text and msg.get("status") == "completed":
                self._pending.append(AgentText(self._response_text, final=True))
            self._response_id = None
            self._response_text = ""
            return

        if kind == p.PROGRESS:
            # The runtime's count is authoritative: it steps the model, we only
            # feed it. Taking the larger of the two keeps the cap honest if a
            # frame was ever dropped on the way in.
            self._model_frames = max(self._model_frames, int(msg.get("frames") or 0))
            if self._model_frames >= self._cfg.max_session_frames:
                self._exhausted()
            return

        if kind == p.ERROR:
            error = msg.get("error") or {}
            if error.get("code") in ("bad_say", "say_mid_turn"):
                self._says_unstarted = max(0, self._says_unstarted - 1)  # refused, not coming
            self._pending.append(
                BackendError(
                    "%s: %s" % (error.get("code", "error"), error.get("message", "")),
                    fatal=bool(error.get("fatal")),
                )
            )
            if error.get("fatal"):
                self._shutdown()
            return

        if kind == p.CLOSED:
            if not self._stopping:
                self._fail("the speech runtime closed the session: %s" % msg.get("reason"))
            return

    def _take_audio(self, msg: Dict[str, Any]) -> None:
        if self._interrupted:
            return  # audio for a response the caller already cut off
        try:
            pcm = p.decode_output_audio(msg)
        except p.ProtocolError as exc:
            self._pending.append(BackendError("bad agent audio: %s" % exc, fatal=False))
            return
        per_frame = self._audio.output_frame_samples * 2
        parts = max(1, len(pcm) // per_frame)
        for chunk in p.split_output_frame(pcm, parts):
            self._playout.append(
                AudioFrame(chunk, self._audio.output_sample_rate, self._out_clock)
            )
            self._out_clock += len(chunk) / 2.0 / self._audio.output_sample_rate

    # --- failing safe ---------------------------------------------------------

    def _check_watchdog(self) -> None:
        """End the call rather than leave a candidate on a silent line.

        Counted in caller frames, not seconds. The failure this guards against is
        the model process wedging while the media path is healthy, and in that
        failure the caller keeps talking, so frames keep arriving.
        """
        if self._frames_since_message < self._cfg.watchdog_frames:
            return
        seconds = self._frames_since_message * self._audio.frame_ms / 1000.0
        self._fail("the speech runtime went silent for %.1f s" % seconds)

    def _exhausted(self) -> None:
        """The session ran out of model frames.

        Reported as an error because in our design it means the interview wall
        clock above failed: a clean call ends 90 seconds before this point.
        """
        self._fail(
            "session frame budget exhausted at %d frames (%.0f minutes)"
            % (self._model_frames, self._model_frames * p.FRAME_MS / 60000.0)
        )

    def _fail(self, message: str) -> None:
        if self._closed:
            return
        self._pending.append(BackendError(message, fatal=True))
        self._shutdown()

    # --- introspection, for tests and logs ------------------------------------

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def model_frames(self) -> int:
        return self._model_frames

    @property
    def discarded_frames(self) -> int:
        """Caller frames thrown away while waiting for the runtime to be ready."""
        return self._discarded_frames


# --- The backend -------------------------------------------------------------


class GB10Backend(VoiceBackend):
    """Opens sessions against the speech runtime. One at a time.

    The model is batch-one and stateful, so a second concurrent session would not
    be a second conversation — it would be the same one with two people talking
    into it. Refusing is the honest behaviour and the scaling answer is a second
    box, which is also the business model.
    """

    name = "gb10"

    def __init__(
        self,
        config: Optional[BackendConfig] = None,
        runtime: Optional[GB10Config] = None,
        link_factory: Optional[Any] = None,
    ) -> None:
        self._config = config or BackendConfig(kind="gb10")
        self._runtime = runtime or GB10Config()
        self._link_factory = link_factory or self._default_link
        self._live: Optional[GB10Session] = None

    def _default_link(self) -> Link:
        return WebSocketLink(self._runtime.url, self._runtime.connect_timeout_s)

    def start_session(
        self,
        system_prompt: str,
        greeting: Optional[str] = None,
    ) -> VoiceSession:
        if self._live is not None and not self._live.closed:
            raise RuntimeError(
                "a conversation is already in progress. This box runs one at a time."
            )
        session = GB10Session(
            self._link_factory(),
            system_prompt,
            greeting=greeting,
            audio=self._config.audio,
            config=self._runtime,
        )
        self._live = session
        return session

    def warmup(self) -> None:
        """Check the runtime is up before anyone is on the line.

        The weights are already resident in the other process, so there is nothing
        here to warm. What there is to do is fail now rather than in front of a
        candidate, so this opens a connection, waits for the runtime to introduce
        itself, and closes it.
        """
        link = self._link_factory()
        try:
            for msg in link.drain():
                if msg.get("type") == p.READY:
                    return
        finally:
            link.close()

    def close(self) -> None:
        if self._live is not None:
            self._live.close()
            self._live = None


def frames_for_seconds(seconds: float, frame_ms: int = p.FRAME_MS) -> int:
    """Model frames in `seconds`. Used for budgets and for reading logs."""
    return int(math.ceil(seconds * 1000.0 / frame_ms))
