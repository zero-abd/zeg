"""Precision and recall of zeg-gaze's flagged spans against labelled clips.

    python services/vision/eval/eval.py [--split test] [--sets real,synth] [--json out.json]

Ground truth is a label every 0.5 s (labels.json for the real clips, written by a
person looking at the frames; synth/labels.json for the synthetic ones, written by
the generator). Spans are derived from those samples with the same rules the detector
uses: a run of one reason, where a single differing sample does not break it, flagged
when it lasts at least the threshold, and flagged runs of one reason less than 1 s apart
merged. A predicted flag matches a true one when they share a reason and their
intersection over union is at least 0.5, one to one, greedily by IoU.

Also reported: the same with the reason ignored (a head turned so far that no face is
found is a "no face" flag over a "looking away" truth), and per-sample label accuracy.

Standard library only. Runs the `zeg-gaze` binary from services/vision/build.
"""

import argparse
import csv
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
VISION = os.path.dirname(HERE)
DEFAULT_CLI = os.path.join(VISION, "build", "zeg-gaze")

REASON = {
    "away_left": "looking_away",
    "away_right": "looking_away",
    "away_down": "looking_away",
    "no_face": "no_face",
    "multiple_faces": "multiple_faces",
}
THRESHOLDS = {"looking_away": 5.0, "no_face": 5.0, "multiple_faces": 2.0}
MERGE_GAP_S = 1.0
IOU_MATCH = 0.5
LABELS = ["on_screen", "away_left", "away_right", "away_down", "no_face", "multiple_faces"]


def truth_spans(samples, step, thresholds=THRESHOLDS):
    """Flag-worthy spans from (t, label) samples, by the detector's own rules."""
    spans = []
    for reason in set(REASON.values()):
        mine = [REASON.get(label) == reason for _, label in samples]
        i = 0
        while i < len(mine):
            if not mine[i]:
                i += 1
                continue
            start = i
            last = i
            j = i + 1
            while j < len(mine):
                if mine[j]:
                    last = j
                elif j - last > 1:  # more than one sample (0.5 s) away ends the run
                    break
                j += 1
            t0 = samples[start][0]
            t1 = samples[last][0] + step
            if t1 - t0 >= thresholds[reason] - 1e-9:
                spans.append({"start_s": t0, "end_s": t1, "reason": reason})
            i = last + 1
    return merge(spans)


def merge(spans, gap=MERGE_GAP_S):
    out = []
    for s in sorted(spans, key=lambda s: s["start_s"]):
        prev = next((p for p in reversed(out) if p["reason"] == s["reason"]), None)
        if prev is not None and s["start_s"] - prev["end_s"] < gap:
            prev["end_s"] = max(prev["end_s"], s["end_s"])
        else:
            out.append(dict(s))
    return out


def iou(a, b):
    inter = max(0.0, min(a["end_s"], b["end_s"]) - max(a["start_s"], b["start_s"]))
    union = (a["end_s"] - a["start_s"]) + (b["end_s"] - b["start_s"]) - inter
    return inter / union if union > 0 else 0.0


def match(pred, truth, strict=True):
    """Greedy one-to-one matching by IoU. Returns the number of matched pairs."""
    pairs = []
    for i, p in enumerate(pred):
        for j, t in enumerate(truth):
            if strict and p["reason"] != t["reason"]:
                continue
            v = iou(p, t)
            if v >= IOU_MATCH:
                pairs.append((v, i, j))
    used_p, used_t = set(), set()
    for v, i, j in sorted(pairs, reverse=True):
        if i not in used_p and j not in used_t:
            used_p.add(i)
            used_t.add(j)
    return len(used_p)


def run_cli(cli, path, threshold):
    frames_csv = path + ".frames.csv"
    out = subprocess.run(
        [cli, path, "--out", "-", "--per-frame", frames_csv, "--threshold", str(threshold)],
        check=True, capture_output=True, text=True,
    )
    flags = json.loads(out.stdout)
    with open(frames_csv) as fh:
        frames = list(csv.DictReader(fh))
    os.remove(frames_csv)
    return flags, frames, out.stderr.strip()


def label_at(frames, t):
    """The detector's final label for the frame nearest time t."""
    lo, hi = 0, len(frames) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if float(frames[mid]["t_s"]) < t:
            lo = mid + 1
        else:
            hi = mid
    best = lo
    if lo > 0 and abs(float(frames[lo - 1]["t_s"]) - t) < abs(float(frames[lo]["t_s"]) - t):
        best = lo - 1
    return frames[best]["label"]


def load_set(name):
    if name == "real":
        base, clips_dir = HERE, os.path.join(HERE, "clips")
    else:
        base = clips_dir = os.path.join(HERE, "synth")
    clips_path, labels_path = os.path.join(base, "clips.json"), os.path.join(base, "labels.json")
    if not (os.path.exists(clips_path) and os.path.exists(labels_path)):
        return []
    with open(clips_path) as fh:
        clips = json.load(fh)
    with open(labels_path) as fh:
        labels = json.load(fh)
    out = []
    for c in clips:
        video = os.path.join(clips_dir, c["id"] + ".avi")
        if c["id"] in labels and os.path.exists(video):
            out.append((name, c, labels[c["id"]], video))
    return out


def pct(n, d):
    return "%5.1f%%" % (100.0 * n / d) if d else "    -"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--cli", default=DEFAULT_CLI)
    ap.add_argument("--split", default="test", help="dev, test or all")
    ap.add_argument("--sets", default="real,synth")
    ap.add_argument("--threshold", type=float, default=5.0)
    ap.add_argument("--json", help="write the numbers here")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args(argv)

    clips = []
    for name in args.sets.split(","):
        clips += load_set(name.strip())
    clips = [c for c in clips if args.split == "all" or c[1].get("split") == args.split]
    if not clips:
        print("no clips found: run `make vision-eval-data` first", file=sys.stderr)
        return 1
    thresholds = dict(THRESHOLDS, looking_away=args.threshold, no_face=args.threshold)

    totals = defaultdict(Counter)   # set -> counts
    by_reason = defaultdict(Counter)  # (set, reason) -> counts
    confusion = defaultdict(Counter)  # (set) -> Counter((truth, pred))
    per_clip = []
    for set_name, clip, lab, video in clips:
        flags, frames, summary = run_cli(args.cli, video, args.threshold)
        samples = [(float(t), label) for t, label in lab["samples"]]
        truth = truth_spans(samples, float(lab.get("step_s", 0.5)), thresholds)
        strict = match(flags, truth, strict=True)
        loose = match(flags, truth, strict=False)
        t = totals[set_name]
        t["pred"] += len(flags)
        t["truth"] += len(truth)
        t["tp"] += strict
        t["tp_any_reason"] += loose
        t["clips"] += 1
        for reason in THRESHOLDS:
            p = [f for f in flags if f["reason"] == reason]
            g = [s for s in truth if s["reason"] == reason]
            c = by_reason[(set_name, reason)]
            c["pred"] += len(p)
            c["truth"] += len(g)
            c["tp"] += match(p, g)
        for ts, label in samples:
            confusion[set_name][(label, label_at(frames, ts))] += 1
        per_clip.append({"set": set_name, "id": clip["id"], "truth": truth, "flags": flags,
                         "tp": strict, "summary": summary})
        if args.verbose:
            print("%-18s truth %d  flags %d  matched %d   %s" % (clip["id"], len(truth), len(flags), strict, summary))
            for s in truth:
                print("    truth %6.1f-%6.1f %s" % (s["start_s"], s["end_s"], s["reason"]))
            for f in flags:
                print("    flag  %6.1f-%6.1f %s %s %.2f" % (f["start_s"], f["end_s"], f["reason"],
                                                          f.get("direction", ""), f["confidence"]))

    print("\nSplit: %s. A flag matches a true span of the same reason at IoU >= %.1f." % (args.split, IOU_MATCH))
    print("\n| set | clips | true spans | flags | matched | precision | recall | recall, any reason |")
    print("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    results = {"split": args.split, "sets": {}}
    for set_name, t in sorted(totals.items()):
        print("| %s | %d | %d | %d | %d | %s | %s | %s |" % (
            set_name, t["clips"], t["truth"], t["pred"], t["tp"], pct(t["tp"], t["pred"]),
            pct(t["tp"], t["truth"]), pct(t["tp_any_reason"], t["truth"])))
        results["sets"][set_name] = dict(t)
    print("\n| set | reason | true spans | flags | matched | precision | recall |")
    print("| --- | --- | ---: | ---: | ---: | ---: | ---: |")
    for (set_name, reason), c in sorted(by_reason.items()):
        if c["pred"] or c["truth"]:
            print("| %s | %s | %d | %d | %d | %s | %s |" % (
                set_name, reason, c["truth"], c["pred"], c["tp"], pct(c["tp"], c["pred"]), pct(c["tp"], c["truth"])))
        results["sets"].setdefault(set_name, {}).setdefault("by_reason", {})[reason] = dict(c)
    for set_name, conf in sorted(confusion.items()):
        n = sum(conf.values())
        right = sum(v for (a, b), v in conf.items() if a == b)
        print("\nPer-sample label accuracy, %s: %s of %d samples (rows truth, columns detector)" % (
            set_name, pct(right, n).strip(), n))
        print("\n| truth \\ detector | " + " | ".join(LABELS) + " |")
        print("| --- |" + " ---: |" * len(LABELS))
        for a in LABELS:
            row = [conf[(a, b)] for b in LABELS]
            if sum(row):
                print("| %s | %s |" % (a, " | ".join(str(v) for v in row)))
        results["sets"][set_name]["sample_accuracy"] = right / n if n else None
        results["sets"][set_name]["samples"] = n
    results["clips"] = per_clip
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(results, fh, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
