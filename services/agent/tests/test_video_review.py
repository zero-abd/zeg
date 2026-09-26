"""The report's "Video review" section: moments for a human to watch, never a verdict."""

import json

from zeg.conversation import TranscriptEntry as T
from zeg.report import assemble_report
from zeg.video_review import VideoFlag, flags_from, load_flags, render_video_review

GAZE_JSON = [
    {"start_s": 192.4, "end_s": 200.9, "reason": "looking_away", "direction": "left",
     "confidence": 0.87, "sample_frame": 2958, "sample_t_s": 196.6},
    {"start_s": 31.0, "end_s": 44.2, "reason": "no_face", "confidence": 0.8,
     "sample_frame": 566, "sample_t_s": 37.7},
    {"start_s": 400.0, "end_s": 403.1, "reason": "multiple_faces", "confidence": 0.9,
     "sample_frame": 6045},
]


def _call():
    return [
        T(0, "agent", "Tell me about the hardest bug you shipped a fix for."),
        T(30, "caller", "I rebuilt the billing export and cut p99 to 40 ms myself"),
    ]


def test_the_section_lists_each_flag_with_its_timestamps_in_order():
    lines = render_video_review(flags_from(GAZE_JSON))
    assert lines[0] == "Video review, moments for a human to watch:"
    body = "\n".join(lines)
    assert "[00:31-00:44] No face in view for 13 s." in body
    assert "[03:12-03:20] Looking away from the screen, to their left, for 8 s." in body
    assert "[06:40-06:43] More than one face in view for 3 s." in body
    assert body.index("00:31") < body.index("03:12") < body.index("06:40")
    assert "Detector agreement 87%" in body


def test_the_wording_is_for_review_never_an_accusation():
    body = "\n".join(render_video_review(flags_from(GAZE_JSON))).lower()
    for word in ("cheat", "suspicious", "dishonest", "violation", "integrity", "fraud"):
        assert word not in body
    assert "not conclusions" in body
    assert "none of it is in the score" in body


def test_no_video_means_no_section_and_an_empty_one_says_it_was_checked():
    assert render_video_review(None) == []
    lines = render_video_review([])
    assert len(lines) == 2 and "Nothing met a threshold" in lines[1]


def test_the_report_carries_the_section_after_the_flags():
    a = assemble_report(_call(), consent=True, interview_started_s=0, wrapped_up_s=40,
                        video_review=GAZE_JSON)
    page = a.render()
    assert "Video review, moments for a human to watch:" in page
    assert page.index("Video review") < page.index("A human reviews this before any decision")
    assert all(isinstance(f, VideoFlag) for f in a.video_review)


def test_video_flags_never_change_the_score():
    """The scorer never sees them. A flag is a moment to watch, not evidence."""
    plain = assemble_report(_call(), consent=True, interview_started_s=0, wrapped_up_s=40)
    flagged = assemble_report(_call(), consent=True, interview_started_s=0, wrapped_up_s=40,
                              video_review=GAZE_JSON)
    assert plain.overall == flagged.overall
    assert plain.band == flagged.band
    assert plain.flags == flagged.flags
    assert [d.score for d in plain.dimensions] == [d.score for d in flagged.dimensions]


def test_an_audio_only_call_has_no_video_section():
    page = assemble_report(_call(), consent=True, interview_started_s=0).render()
    assert "Video review" not in page


def test_the_interview_hands_video_flags_to_its_report():
    from zeg.backends.base import AgentText, UserTranscript
    from zeg.interview import Interview

    iv = Interview()
    iv.start()
    iv.on_event(UserTranscript("yes that is fine", final=True), 5)
    iv.on_event(AgentText("What did you personally do?", final=True), 20)
    iv.on_event(UserTranscript("I wrote the advisory-lock fix myself", final=True), 40)
    page = iv.report(video_review=GAZE_JSON[:1]).render()
    assert "[03:12-03:20] Looking away" in page


def test_zeg_gaze_output_loads_from_disk_and_moves_onto_the_call_clock(tmp_path):
    path = tmp_path / "flags.json"
    path.write_text(json.dumps(GAZE_JSON))
    flags = load_flags(str(path))
    assert [f.reason for f in flags] == ["no_face", "looking_away", "multiple_faces"]
    shifted = load_flags(str(path), offset_s=12.0)
    assert shifted[0].start_s == 43.0 and shifted[0].sample_frame == 566
    # The Python module returns {"flags": [...], ...}; accept that too.
    path.write_text(json.dumps({"flags": GAZE_JSON, "frames": 9000}))
    assert len(load_flags(str(path))) == 3


def test_directions_and_unknown_reasons_read_plainly():
    down = VideoFlag(0, 6, "looking_away", direction="down")
    assert down.describe() == "Looking down, away from the screen, for 6 s."
    mixed = VideoFlag(0, 9.6, "looking_away", direction="mixed")
    assert mixed.describe() == "Looking away from the screen, for 10 s."
    assert VideoFlag(0, 3, "camera_covered").describe() == "Camera covered for 3 s."


def test_the_cli_puts_video_flags_in_the_demo_report(tmp_path, capsys):
    from zeg.cli import main

    path = tmp_path / "flags.json"
    path.write_text(json.dumps(GAZE_JSON[:1]))
    assert main(["--quiet", "--video-flags", str(path)]) == 0
    out = capsys.readouterr().out
    assert "Video review, moments for a human to watch:" in out
    assert "[03:12-03:20] Looking away from the screen, to their left, for 8 s." in out
