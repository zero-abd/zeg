// zeg-gaze: face presence and gaze direction from a webcam feed, with Haar cascades.
//
// Every frame is classified as on screen, looking away (left, right, down), no face,
// or more than one face. A short median and majority filter removes single-frame
// noise, and a segmenter turns long runs of anything other than "on screen" into
// spans a human can review. See docs/12-video-review.md for how each step works and
// where it breaks.
//
// The flags are moments for a person to look at. They are never a finding about the
// candidate, and nothing downstream may treat them as one (docs/06-compliance.md).
#pragma once

#include <cstdint>
#include <deque>
#include <functional>
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include <opencv2/core.hpp>
#include <opencv2/objdetect.hpp>

namespace zeg::gaze {

// What one frame shows. Left and right are the candidate's own left and right, so a
// candidate turning to their left moves toward the right of an unmirrored camera image.
enum class Label : int {
    OnScreen = 0,
    AwayLeft,
    AwayRight,
    AwayDown,
    NoFace,
    MultipleFaces,
};

const char* label_name(Label label);
std::optional<Label> label_from_name(const std::string& name);
bool is_away(Label label);

// The reason a span is flagged. Looking away left, right or down all count toward one
// continuous "looking away" span; the direction is reported beside it.
enum class Reason : int { LookingAway = 0, NoFace, MultipleFaces };
const char* reason_name(Reason reason);
std::optional<Reason> reason_for(Label label);

struct Config {
    // Detection. Frames are searched for faces at `detect_width` pixels wide, which is
    // most of the speed; eyes are searched at full resolution inside the face.
    int detect_width = 320;
    int max_width = 640;               // larger frames are scaled down to this first
    double face_scale_factor = 1.1;
    int face_min_neighbors = 5;
    // The profile cascade runs only when no frontal face was found, so it can afford a
    // finer scale step; at 1.1 it missed turned heads depending on how the frame was scaled.
    double profile_scale_factor = 1.05;
    int profile_min_neighbors = 4;
    double min_face_fraction = 0.10;  // smallest face, as a fraction of frame width

    // Gaze. Offsets are fractions of the eye (pupil) or face (head yaw) width, measured
    // against the candidate's own running baseline, so a camera mounted above the
    // screen does not read as "always looking down".
    double horizontal_threshold = 0.20;
    double down_threshold = 0.16;
    double yaw_weight = 1.5;           // head yaw counts this much toward the horizontal offset
    double baseline_window_s = 30.0;   // how far back the baseline looks
    int baseline_min_frames = 15;      // before this many, the baseline is zero

    // Smoothing: a median over the last `smooth_window` offsets, and the label of each
    // frame is the majority over a window of that many frames centred on it.
    int smooth_window = 9;

    // Segments.
    double away_threshold_s = 5.0;       // plan.md: gaze away for more than 5 s
    double no_face_threshold_s = 5.0;
    double multi_face_threshold_s = 2.0;
    double max_gap_s = 0.5;   // an interruption shorter than this does not end a run
    double merge_gap_s = 1.0; // flagged spans of one reason closer than this are merged
};

struct EyeResult {
    cv::Rect box;          // in frame coordinates
    cv::Point2d pupil;     // in frame coordinates
    bool pupil_found = false;
    double dx = 0.0;       // pupil offset from the eye centre, fraction of eye width, + = image right
    double dy = 0.0;       // fraction of eye height, + = down
};

struct FaceResult {
    cv::Rect box;          // in frame coordinates
    bool profile = false;  // found by the profile cascade, not the frontal one
    bool facing_image_right = false;  // for a profile: which way the nose points
};

// Everything the detector saw in one frame, before any smoothing.
struct FrameObservation {
    int64_t index = 0;
    double t_s = 0.0;
    std::vector<FaceResult> faces;  // primary face first
    std::vector<EyeResult> eyes;    // eyes of the primary face, up to two
    bool has_offsets = false;       // pupil or yaw evidence available
    double h_offset = 0.0;          // + = image right = the candidate's left
    double v_offset = 0.0;          // + = down
    double yaw = 0.0;               // eye midpoint vs face centre, fraction of face width
};

// A frame after classification.
struct FrameResult {
    int64_t index = 0;
    double t_s = 0.0;
    Label raw = Label::NoFace;      // this frame on its own
    Label label = Label::NoFace;    // after the majority filter
    double confidence = 0.0;        // how sure the raw label is, 0..1
    int faces = 0;
    int eyes = 0;
    double h_offset = 0.0;          // smoothed, relative to baseline
    double v_offset = 0.0;
};

struct Flag {
    double start_s = 0.0;
    double end_s = 0.0;
    Reason reason = Reason::LookingAway;
    std::string direction;      // for looking away: left, right, down or mixed
    double confidence = 0.0;    // share of raw frames in the span that agree, weighted by frame confidence
    int64_t sample_frame = 0;   // frame index in the middle of the span
    double sample_t_s = 0.0;
    std::string sample_image;   // path, when the caller saved one
};

// ---------------------------------------------------------------------------------
// Pupil localisation inside one eye patch (grayscale). Returns the pupil centre in
// patch coordinates, or nothing when no dark blob stands out.
std::optional<cv::Point2d> locate_pupil(const cv::Mat& eye_gray);

// Finds faces and eyes with the Haar cascades. Stateless between frames.
class Detector {
public:
    // `cascade_dir` holds haarcascade_*.xml. Empty means the directory found at build
    // time, or $ZEG_GAZE_CASCADES when set.
    explicit Detector(const Config& config = Config(), const std::string& cascade_dir = "");
    FrameObservation observe(const cv::Mat& bgr, double t_s, int64_t index) const;
    const Config& config() const { return config_; }

private:
    Config config_;
    mutable cv::CascadeClassifier frontal_, profile_, eye_, eye_glasses_;
    std::vector<EyeResult> find_eyes(const cv::Mat& gray, const cv::Rect& face) const;
    bool has_an_eye(const cv::Mat& gray, const cv::Rect& face) const;
};

std::string default_cascade_dir();

// Classifies a frame from its observation and the candidate's baseline. Pure.
struct Classification {
    Label label;
    double confidence;
};
Classification classify(const FrameObservation& obs, double h_rel, double v_rel,
                        bool eyes_usually_found, const Config& config);

// Turns a stream of smoothed frames into flagged spans. Feed frames in time order.
class Segmenter {
public:
    explicit Segmenter(const Config& config = Config());
    void push(const FrameResult& frame);
    // Spans closed since the last call. A span still open is not returned until it ends.
    std::vector<Flag> take_closed();
    // Close whatever is open and return every remaining flag.
    std::vector<Flag> finish();

private:
    struct Run {
        bool open = false;
        double start_s = 0.0, last_s = 0.0;
        std::vector<FrameResult> frames;  // frames inside the run, for confidence and direction
    };
    Config config_;
    Run runs_[3];
    double dt_ = 0.0;
    double last_t_ = -1.0;
    std::vector<Flag> closed_;   // thresholded, not yet merged
    std::vector<Flag> ready_;    // merged, safe to hand out
    void close_run(int reason, double end_s);
    void release(bool all, double now_s);
    double threshold_for(Reason reason) const;
};

// Merge flagged spans of the same reason that are closer than `gap_s`, sorted by start.
std::vector<Flag> merge_flags(std::vector<Flag> flags, double gap_s);

// The whole pipeline for one call: detector, baseline, smoothing, segmenter. Works on
// live frames: push each frame as it arrives, read closed flags whenever you like, and
// call finish() when the call ends.
class Session {
public:
    explicit Session(const Config& config = Config(), const std::string& cascade_dir = "");
    ~Session();
    Session(const Session&) = delete;
    Session& operator=(const Session&) = delete;

    // Raw BGR pixels, 3 bytes per pixel, `stride` bytes per row (0 = width * 3).
    // Returns the frame results that became final with this push (the majority filter
    // delays each label by half its window).
    std::vector<FrameResult> push_bgr(const uint8_t* data, int width, int height, size_t stride,
                                      double t_s);
    std::vector<FrameResult> push(const cv::Mat& bgr, double t_s);
    std::vector<Flag> take_closed();
    std::vector<Flag> finish();

    int64_t frames() const { return next_index_; }
    const Config& config() const { return config_; }

    // Optional hook: called with the frame and its result as each result becomes final,
    // e.g. to save a still for a flagged span. The frame is only kept when a hook is set.
    std::function<void(const FrameResult&, const cv::Mat&)> on_final;

private:
    struct Impl;
    Config config_;
    std::unique_ptr<Impl> impl_;
    int64_t next_index_ = 0;
};

// Post-call: run a video file through a Session. `sample_dir`, when not empty, gets a
// JPEG of the middle frame of every flagged span. `per_frame`, when set, receives every
// final frame result. Throws std::runtime_error when the file cannot be opened.
struct VideoSummary {
    std::vector<Flag> flags;
    int64_t frames = 0;
    double duration_s = 0.0;
    double processing_fps = 0.0;  // decode plus analysis
    double analysis_fps = 0.0;    // analysis alone
    int width = 0, height = 0;
};
VideoSummary process_video(const std::string& path, const Config& config = Config(),
                           const std::string& cascade_dir = "", const std::string& sample_dir = "",
                           const std::function<void(const FrameResult&)>& per_frame = nullptr);

std::string flags_to_json(const std::vector<Flag>& flags, int indent = 2);

}  // namespace zeg::gaze
