"""Moments of the call video for a human to look at.

The vision service (services/vision, `zeg-gaze`) watches the candidate's camera, when
they chose to send it, and marks spans where they looked away from the screen for a
while, where no face was in view, or where more than one face was. This module is the
agent's side of that: the flag shape, reading it from the service's JSON, and the
"Video review" section of the report.

Standard library only, like the rest of the agent. The detector is optional and lives
in another process or module; the report must build without it.

What a flag is, and is not. It marks video worth watching. It is not a finding about
the candidate, and nothing here scores it or feeds it to the scorer: a person looks
away to think, to read notes they were allowed, at a second monitor, at a child who
walked in. A face drops out when a laptop lid moves. docs/06-compliance.md: a human
reviews every report before any decision, and these moments are part of what they
review, not a conclusion handed to them. docs/12-video-review.md has the detail.
"""

import json
from dataclasses import dataclass
from typing import Iterable, List, Mapping, Optional, Sequence

#: The reasons zeg-gaze emits. Anything else is shown under its own name rather than
#: dropped, so a newer detector cannot silently lose a flag in an older report.
REASONS = ("looking_away", "no_face", "multiple_faces")


@dataclass(frozen=True)
class VideoFlag:
    start_s: float
    end_s: float
    reason: str
    confidence: float = 0.0
    direction: str = ""
    sample_frame: Optional[int] = None
    sample_image: str = ""

    @classmethod
    def from_dict(cls, d: Mapping) -> "VideoFlag":
        return cls(
            start_s=float(d["start_s"]),
            end_s=float(d["end_s"]),
            reason=str(d["reason"]),
            confidence=float(d.get("confidence", 0.0)),
            direction=str(d.get("direction", "") or ""),
            sample_frame=int(d["sample_frame"]) if d.get("sample_frame") is not None else None,
            sample_image=str(d.get("sample_image", "") or ""),
        )

    @property
    def duration_s(self) -> float:
        return max(0.0, self.end_s - self.start_s)

    def shifted(self, offset_s: float) -> "VideoFlag":
        """The same flag on the call's clock, when the video started `offset_s` in."""
        return VideoFlag(
            self.start_s + offset_s, self.end_s + offset_s, self.reason, self.confidence,
            self.direction, self.sample_frame, self.sample_image,
        )

    def describe(self) -> str:
        """What happened, in plain words, with no guess at why."""
        secs = "%d s" % round(self.duration_s)
        if self.reason == "looking_away":
            where = {
                "left": "Looking away from the screen, to their left",
                "right": "Looking away from the screen, to their right",
                "down": "Looking down, away from the screen",
            }.get(self.direction, "Looking away from the screen")
            return "%s, for %s." % (where, secs)
        if self.reason == "no_face":
            return "No face in view for %s." % secs
        if self.reason == "multiple_faces":
            return "More than one face in view for %s." % secs
        return "%s for %s." % (self.reason.replace("_", " ").capitalize(), secs)


def flags_from(items: Iterable[Mapping]) -> List[VideoFlag]:
    """Flags from zeg-gaze's JSON list (or the Python module's dicts), in time order."""
    return sorted((VideoFlag.from_dict(d) for d in items), key=lambda f: f.start_s)


def load_flags(path: str, offset_s: float = 0.0) -> List[VideoFlag]:
    """Read `zeg-gaze --out` output. `offset_s` moves them onto the call clock."""
    with open(path) as fh:
        data = json.load(fh)
    if isinstance(data, Mapping):  # tolerate {"flags": [...]} as the module returns
        data = data.get("flags", [])
    return [f.shifted(offset_s) if offset_s else f for f in flags_from(data)]


def _clock(t: float) -> str:
    mins, secs = divmod(int(t), 60)
    return "%02d:%02d" % (mins, secs)


def render_video_review(flags: Optional[Sequence[VideoFlag]]) -> List[str]:
    """The report's "Video review" section, as lines. Empty when there was no video.

    `None` means no video was analysed (the camera is optional, and the screen is audio
    first), so the section is left out. An empty list means the video was watched and
    nothing met a threshold, which a reviewer should be told rather than left to guess.
    """
    if flags is None:
        return []
    out = ["Video review, moments for a human to watch:"]
    if not flags:
        out.append("  Nothing met a threshold. The candidate's camera was analysed.")
        return out
    for f in sorted(flags, key=lambda f: f.start_s):
        line = "  [%s-%s] %s" % (_clock(f.start_s), _clock(f.end_s), f.describe())
        if f.confidence:
            line += " Detector agreement %d%%." % round(100 * f.confidence)
        out.append(line)
    out.append(
        "  These mark video to watch, not conclusions. People look away to think, read "
        "notes, or check a second screen, and a face drops out when a camera moves. "
        "Watch the moment before weighing it; none of it is in the score."
    )
    return out
