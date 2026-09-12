"""The playback jitter buffer, and the barge-in flush.

A FIFO of PCM16 bytes at the playback rate. The outbound audio track pulls a
fixed frame from it every 20 ms; when the buffer runs dry it serves silence, so
the RTP stream stays alive between the agent's turns.

`flush()` is the whole point of this file. When the model reports the caller cut
in (AgentInterrupted), everything already queued has to vanish immediately, or
the candidate hears the agent keep talking over them. The gateway README calls
this the single most visible quality signal in a voice agent, so it is one
method with no cleverness in it: drop the bytes, now.
"""


class PlaybackBuffer:
    """Rate-agnostic PCM16 FIFO with an instant flush."""

    def __init__(self, sample_rate: int) -> None:
        self.sample_rate = sample_rate
        self._buf = bytearray()

    def enqueue(self, pcm: bytes) -> None:
        self._buf.extend(pcm)

    def take(self, n_samples: int) -> bytes:
        """Return exactly `n_samples` (2 bytes each), silence-padded if short."""
        need = n_samples * 2
        if len(self._buf) >= need:
            out = bytes(self._buf[:need])
            del self._buf[:need]
            return out
        out = bytes(self._buf) + b"\x00" * (need - len(self._buf))
        self._buf.clear()
        return out

    def flush(self) -> None:
        """Barge-in. Drop everything queued for playback."""
        self._buf.clear()

    def __len__(self) -> int:
        """Samples currently buffered."""
        return len(self._buf) // 2
