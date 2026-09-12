# Track 2 (gateway) — handoff & orientation

Written for a teammate or a fresh Claude session picking this up, and for anyone who
wants to understand what this project actually is without reverse-engineering the code.

---

## 1. What the whole project is, in plain English

**zeg is a robot interviewer.** A job candidate joins a call, an AI talks to them like
a screening interviewer for a software job (asks questions, follows up, probes claims),
and afterward it produces a 1–10 assessment with quotes for a human recruiter to review.

The selling point: it runs **entirely on one computer** (a ~$5K Dell box), so the
candidate's voice never leaves the room. No cloud vendor, no per-interview fee, no data
compliance headache. A human still makes the actual hiring decision.

Think of the system as two halves:

- **The brain** (`services/agent/`) — decides *what to say*. Already largely built by
  Abdullah. It can run with a **fake voice** ("mock backend") so the rest of the team
  can work without the real AI model or a GPU.
- **The phone line** (`services/gateway/` = **Track 2, this folder**) — carries the
  candidate's *audio in and out*. It gets the candidate's microphone into the brain and
  plays the brain's replies back to them. **This is what I built.**

There's also a `web/` marketing landing page (unrelated to the interview itself) and a
`docs/` folder with Abdullah's design reasoning.

---

## 2. Words that are confusing until they aren't

| Term | Plain meaning |
|---|---|
| **backend** | The thing that produces the AI's voice. Two kinds: **mock** (fake, plays a 220 Hz beep instead of speech, runs on any laptop — for testing) and **gb10** (the real AI model on the Dell box — **not written yet**). |
| **VoiceSession** | The brain's "socket." You *push* the candidate's audio into it and *poll* it for what the AI wants to say. Track 2's whole job is to feed this and play back what comes out. Defined in `services/agent/zeg/backends/base.py`. |
| **PCM16 / sample rate** | Raw audio = a list of numbers, N per second. "16 kHz mono PCM16" = 16,000 numbers/second, one channel, each a 16-bit integer. The AI *hears* at 16 kHz and *speaks* at 22.05 kHz. Browsers use 48 kHz, so we **resample** between them. |
| **frame** | A tiny slice of audio, here 20 ms (= 320 numbers at 16 kHz). Audio is streamed as a march of these little frames. |
| **barge-in** | The candidate interrupting the AI mid-sentence. When that happens we must **instantly stop** the AI's playback, or it talks over them. This is the single most important quality behavior. |
| **WebRTC** | The browser tech for real-time audio/video calls. The candidate's page uses it to stream mic (and optionally camera) to our server. |
| **SDP offer/answer** | The handshake WebRTC does to set up a call: browser sends an "offer," server sends back an "answer," then media flows. |
| **aiortc / PyAV** | The Python libraries that let our server speak WebRTC and decode/resample audio. |

---

## 3. How the pieces fit (the audio's journey)

```
 CANDIDATE'S BROWSER                    THE DELL BOX (our server)                 THE BRAIN
 ┌────────────────┐                    ┌──────────────────────────────┐         ┌───────────────┐
 │  mic  ──────────┼──WebRTC (48 kHz)──▶│ webrtc.py: resample→16 kHz,   │         │               │
 │                │                    │ chop into 20 ms frames        │         │               │
 │                │                    │        │                      │  push   │  VoiceSession │
 │                │                    │        ▼                      │ ───────▶│  (mock today, │
 │                │                    │   bridge.py  ─── poll ────────┼────────▶│   gb10 later) │
 │                │                    │        ▲          events:     │         │               │
 │  speaker ◀──────┼──WebRTC (48 kHz)──│ playback.py ◀── AgentAudio     │◀────────│  greeting +   │
 │                │                    │  (upsample 22.05→48 kHz)      │         │  answers      │
 └────────────────┘                    │  flush() on barge-in ◀────────┼── AgentInterrupted      │
                                        └──────────────────────────────┘         └───────────────┘
```

The key idea: **Track 2 is a translator/switchboard.** It does not contain any AI. It
turns browser audio into the exact format the brain wants, hands it over, and plays back
whatever the brain says. The brain is swappable (mock ↔ real) with no change to Track 2.

---

## 4. Repo map (where to look)

```
zeg/
├─ README.md            what the product is + the barebone laptop demo
├─ ONBOARDING.md        read this first (Abdullah's)
├─ plan.md              the build plan and open questions (Abdullah's)
├─ docs/                design decisions with reasoning (00 vision … 11 runtime)
├─ Makefile             all the run/test shortcuts
├─ services/
│  ├─ agent/            THE BRAIN (stdlib-only, no GPU needed for the mock)
│  │  └─ zeg/
│  │     ├─ backends/base.py   ← the VoiceSession contract Track 2 plugs into
│  │     ├─ backends/mock.py   ← fake voice for testing (220 Hz tone)
│  │     ├─ conversation.py    ← drives a *simulated* caller; Track 2 replaces the sim
│  │     ├─ config.py          ← the audio sample rates
│  │     ├─ audio.py           ← AudioFrame + resample helper
│  │     ├─ prompts.py         ← greeting, AI/consent disclosure, system prompt
│  │     └─ runtime/           ← internal brain↔model protocol (NOT Track 2's concern)
│  └─ gateway/          TRACK 2 — everything I built (this folder)
│     ├─ gateway/bridge.py     ← core loop: caller frame in → VoiceSession → events out
│     ├─ gateway/playback.py   ← playback buffer + the barge-in flush()
│     ├─ gateway/framing.py    ← chop audio into exact 20 ms frames
│     ├─ gateway/webrtc.py     ← aiortc adapter (the only file that touches WebRTC/PyAV)
│     ├─ gateway/server.py     ← web server: serves the page, does the SDP handshake
│     ├─ web/interview.html    ← the page the candidate opens
│     ├─ tests/                ← 9 tests, run on any laptop, no WebRTC needed
│     └─ tools/meet_provision.py ← STRETCH ONLY: make a real Google Meet link
└─ web/                 marketing landing page (Next.js) — not the interview
```

**Design split that matters:** `bridge.py`, `playback.py`, `framing.py` contain the
logic and import **no WebRTC**, so they're unit-tested on any laptop. `webrtc.py` is the
only file that needs aiortc/PyAV. That's why the barge-in logic can be tested without a
browser.

---

## 5. How to run and test it

```bash
# one-time, from the repo root
make setup            # creates .venv, installs pytest

# Track 2 logic tests — no browser, no heavy deps (fast)
make gateway-test     # 9 pass: framing, playback, barge-in (against the mock brain)

# the brain's own tests, to confirm nothing upstream broke
make test             # 68 pass

# run the actual server (needs the transport libraries first)
make gateway-setup    # installs aiortc + aiohttp (heavy: pulls PyAV, ~1–2 min)
make gateway          # serves http://localhost:8080  (BACKEND=mock by default)
```

Then open <http://localhost:8080>, click **Join**. With the mock brain you'll hear a
220 Hz tone as its "voice" (that's expected — the mock doesn't do real speech), and you
should be able to interrupt it. For a candidate on another machine you need HTTPS:
`cloudflared tunnel --url http://localhost:8080`.

Switch to the real model later with `make gateway BACKEND=gb10` — **once Track 1 writes
`services/agent/zeg/backends/gb10.py`** (see next section).

---

## 6. Status — done vs. not done (be honest with yourself here)

**Done & verified**
- All gateway code, wired to the brain's `VoiceSession` seam.
- Barge-in / framing / playback logic unit-tested (9/9). Brain suite still 68/68.
- Server boots the full aiortc/PyAV chain; `/healthz` OK; candidate page served; a
  malformed offer is rejected with HTTP 400 and does **not** wedge the single-call slot.
- Committed and pushed: branch `track2-gateway`, **PR #1**
  (https://github.com/zero-abd/zeg/pull/1), open and mergeable. Not merged into `main`.

**NOT done / unverified — the parts that gate a real demo**
1. **No live call has ever actually run.** The browser↔server media handshake and real
   audio in/out were never exercised (couldn't be done headless in the session that
   built this). `webrtc.py` — the outbound audio frame construction, Opus negotiation,
   the inbound resampler — is the least-tested code and the most likely to break on the
   first real call.
2. **The real voice (`gb10` backend) doesn't exist yet.** That's Track 1's deliverable.
   Until it lands, the gateway can only produce a beep, not an interview.
3. **HTTPS tunnel** for a remote candidate isn't set up.
4. **Video** is a stub only (deliberately — the product is audio-only per `docs/00`).
5. **Meet provisioning** is stretch code, needs Google OAuth credentials, untested.

---

## 7. What to do next (in priority order)

1. **Validate the live media path.** Best headless option: write an **aiortc-to-aiortc
   loopback test** — a small Python client that sends an SDP offer to `/offer`, streams
   synthetic audio, and asserts it receives agent audio back. This exercises `webrtc.py`
   (the risky file) without a browser. Then do one **manual browser Join** on the box.
2. **Integrate the real brain** once Track 1 ships `gb10.py`: run `make gateway
   BACKEND=gb10`. No gateway code should need to change — that's the whole point of the
   `VoiceSession` seam. If it does, that's a bug in the seam, not the gateway.
3. **HTTPS** via `cloudflared`/`ngrok` so a candidate can join from their laptop.
4. **Hand the transcript to scoring** at hangup — `bridge.transcript` is a list of
   `(speaker, text)` collected during the call; `server.py::_report` currently just logs
   it. The interview engine (`services/agent/zeg/engine.py`) is where scoring lives.
5. (Stretch) video/gaze: `gateway/webrtc.py::consume_video` has a `video_sink` seam where
   MediaPipe would attach. Only if there's time and the team wants it.

---

## 8. The contracts other tracks rely on (don't break these)

- **Track 1 → Track 2:** provide a backend implementing `VoiceBackend`/`VoiceSession`
  (`services/agent/zeg/backends/base.py`): `push_audio(AudioFrame)`, `poll() -> events`,
  `close()`. The gateway selects it via `build_backend(BackendConfig(kind="gb10"))`.
- **Audio format (from `zeg.config`):** 16 kHz mono PCM16 in, 22.05 kHz out, 20 ms
  frames. The gateway imports these constants — never hardcode different ones.
- **Faithfulness rule for this repo:** match Abdullah's committed conventions and
  contracts; read the relevant `docs/` + module before adding code; when the committed
  plan disagrees with older meeting notes, follow the commits.

## 9. Canonical reading (Abdullah's, authoritative)

Start with `ONBOARDING.md`, then `plan.md`, then `services/gateway/README.md` (the
gateway's own spec), then `docs/01-architecture.md` and `docs/11-runtime.md`.
