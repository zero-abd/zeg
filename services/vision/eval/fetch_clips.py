#!/usr/bin/env python3
"""Download and prepare the gaze / face-presence evaluation clips.

Reads clips.json next to this file. For each clip it:

1. downloads the source video by its exact URL into a cache directory
   (default: services/vision/eval/.cache/) and verifies its sha256;
2. decodes [start_s, end_s) of source time, optionally crops a rectangle
   (``crop: [x, y, w, h]`` in source pixels), scales to 640 px wide (aspect kept,
   even height), and resamples to a constant frame rate (the source rate, capped
   at 30 fps) by holding the latest source frame at each output tick;
3. writes services/vision/eval/clips/<clip_id>.avi as MJPEG (yuvj420p) in an AVI
   container, which OpenCV's built-in reader opens without FFmpeg.

Output time 0 is the trim start, so label time t maps to source time start_s + t.

Only PyAV and the standard library are used. Idempotent: a clip is rebuilt only
when its .avi is missing or clips.json changed the parameters it was built from.

    .venv/bin/python services/vision/eval/fetch_clips.py
    .venv/bin/python services/vision/eval/fetch_clips.py --only kelly_iss_message
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.request
from fractions import Fraction
from pathlib import Path

import av

HERE = Path(__file__).resolve().parent
USER_AGENT = "zeg-vision-eval/0.1 (https://github.com/zero-abd/zeg)"
OUT_WIDTH = 640
MAX_FPS = Fraction(30)
MJPEG_BIT_RATE = 8_000_000


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(clip: dict, cache: Path) -> Path:
    url = clip["source_url"]
    ext = os.path.splitext(url.split("?", 1)[0])[1] or ".bin"
    dest = cache / f"{clip['id']}{ext}"
    if dest.exists() and sha256_of(dest) == clip["sha256"]:
        return dest
    cache.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    print(f"[{clip['id']}] downloading {url}", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp, open(part, "wb") as f:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    got = sha256_of(part)
    if got != clip["sha256"]:
        part.unlink()
        raise SystemExit(
            f"[{clip['id']}] sha256 mismatch: expected {clip['sha256']}, got {got}. "
            "The file on Commons may have been re-uploaded; do not relabel silently."
        )
    part.replace(dest)
    return dest


def build_params(clip: dict) -> dict:
    """The parameters an output clip depends on; used as the rebuild stamp."""
    return {
        "sha256": clip["sha256"],
        "start_s": clip["start_s"],
        "end_s": clip["end_s"],
        "crop": clip.get("crop"),
        "out_width": OUT_WIDTH,
        "max_fps": str(MAX_FPS),
        "bit_rate": MJPEG_BIT_RATE,
    }


def make_graph(stream, crop, out_w: int, out_h: int):
    graph = av.filter.Graph()
    src = graph.add_buffer(template=stream)
    nodes = [src]
    if crop:
        x, y, w, h = crop
        nodes.append(graph.add("crop", f"{w}:{h}:{x}:{y}"))
    nodes.append(graph.add("scale", f"{out_w}:{out_h}:flags=bicubic"))
    nodes.append(graph.add("format", "yuvj420p"))
    sink = graph.add("buffersink")
    nodes.append(sink)
    for a, b in zip(nodes, nodes[1:]):
        a.link_to(b)
    graph.configure()
    return graph


def prepare(clip: dict, src: Path, out: Path) -> None:
    start, end = float(clip["start_s"]), float(clip["end_s"])
    crop = clip.get("crop")
    inp = av.open(str(src))
    vs = inp.streams.video[0]
    vs.thread_type = "AUTO"
    in_w, in_h = (crop[2], crop[3]) if crop else (vs.codec_context.width, vs.codec_context.height)
    out_w = OUT_WIDTH
    out_h = int(round(in_h * out_w / in_w / 2.0)) * 2

    src_rate = vs.average_rate or vs.guessed_rate or Fraction(30)
    rate = Fraction(src_rate) if Fraction(src_rate) <= MAX_FPS else MAX_FPS
    rate = rate.limit_denominator(1001)

    graph = make_graph(vs, crop, out_w, out_h)

    tmp = out.with_suffix(".avi.part")
    outc = av.open(str(tmp), mode="w", format="avi")
    os_ = outc.add_stream("mjpeg", rate=rate)
    os_.width, os_.height = out_w, out_h
    os_.pix_fmt = "yuvj420p"
    os_.bit_rate = MJPEG_BIT_RATE
    os_.codec_context.time_base = Fraction(rate.denominator, rate.numerator)

    n_out = int((end - start) * rate + 1e-9)  # output frames at k / rate, k < n_out
    k = 0
    held = None  # latest processed frame with source time <= current tick

    def emit(frame):
        nonlocal k
        f = frame.reformat(format="yuvj420p") if frame.format.name != "yuvj420p" else frame
        f.pts = k
        f.time_base = os_.codec_context.time_base
        for pkt in os_.encode(f):
            outc.mux(pkt)
        k += 1

    if start > 1.0:
        inp.seek(int((start - 1.0) / vs.time_base), stream=vs, backward=True, any_frame=False)

    for frame in inp.decode(vs):
        if frame.pts is None:
            continue
        t = float(frame.pts * vs.time_base)
        if t < start - 1.0:
            continue
        graph.push(frame)
        while True:
            try:
                pf = graph.pull()
            except (av.error.BlockingIOError, av.error.EOFError):
                break
            pt = float(pf.pts * pf.time_base) if pf.pts is not None else t
            # emit held frame for every tick strictly before this frame's time
            while k < n_out and start + k / rate < pt - 1e-6:
                if held is not None:
                    emit(held)
                else:
                    emit(pf)  # nothing earlier exists; show the first frame
            held = pf
        if k >= n_out or t > end + 1.0:
            break
    while k < n_out and held is not None:
        emit(held)

    for pkt in os_.encode():
        outc.mux(pkt)
    outc.close()
    inp.close()
    tmp.replace(out)
    print(f"[{clip['id']}] wrote {out}: {k} frames @ {float(rate):.3f} fps, "
          f"{out_w}x{out_h}, {float(k / rate):.2f} s", flush=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--only", action="append", default=[], help="clip id (repeatable)")
    ap.add_argument("--cache", type=Path, default=HERE / ".cache", help="download cache dir")
    ap.add_argument("--out", type=Path, default=HERE / "clips", help="output dir for .avi clips")
    ap.add_argument("--force", action="store_true", help="rebuild even if up to date")
    args = ap.parse_args(argv)

    clips = json.loads((HERE / "clips.json").read_text())
    ids = {c["id"] for c in clips}
    unknown = [i for i in args.only if i not in ids]
    if unknown:
        ap.error(f"unknown clip id(s): {', '.join(unknown)}")
    args.out.mkdir(parents=True, exist_ok=True)

    for clip in clips:
        if args.only and clip["id"] not in args.only:
            continue
        out = args.out / f"{clip['id']}.avi"
        stamp = args.out / f"{clip['id']}.params.json"
        params = build_params(clip)
        if (not args.force and out.exists() and stamp.exists()
                and json.loads(stamp.read_text()) == params):
            print(f"[{clip['id']}] up to date")
            continue
        src = download(clip, args.cache)
        prepare(clip, src, out)
        stamp.write_text(json.dumps(params, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
