// The live pipeline (detector, baseline, smoothing, segmenter) and the post-call file path.
#include <algorithm>
#include <chrono>
#include <cmath>
#include <deque>
#include <map>
#include <stdexcept>

#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/videoio.hpp>

#include "zeg_gaze/gaze.hpp"

namespace zeg::gaze {

namespace {

double median(std::vector<double> v) {
    if (v.empty()) return 0.0;
    const size_t mid = v.size() / 2;
    std::nth_element(v.begin(), v.begin() + mid, v.end());
    double m = v[mid];
    if (v.size() % 2 == 0) {
        m = (m + *std::max_element(v.begin(), v.begin() + mid)) / 2.0;
    }
    return m;
}

// A frontal face on its own: the only kind of frame whose eye offsets mean anything.
bool single_frontal(const FrameObservation& obs) {
    return obs.faces.size() == 1 && !obs.faces.front().profile;
}

struct Entry {
    FrameObservation obs;
    double h_rel = 0.0, v_rel = 0.0;
    bool eyes_usual = true;
    Classification raw{Label::NoFace, 0.0};
    Classification pre{Label::NoFace, 0.0};
    double h_med = 0.0, v_med = 0.0;
    cv::Mat frame;  // kept only when the caller installed on_final
};

}  // namespace

struct Session::Impl {
    explicit Impl(const Config& c, const std::string& dir) : config(c), detector(c, dir), segmenter(c) {
        k = std::max(0, config.smooth_window / 2);
    }

    Config config;
    Detector detector;
    Segmenter segmenter;
    int k = 4;

    // The candidate's own resting offsets, and how often their eyes are found at all.
    std::deque<std::pair<double, std::pair<double, double>>> baseline;  // t, (h, v)
    std::deque<std::pair<double, bool>> eye_seen;                       // t, found

    // Stage A centres a window on each frame to take the median of its offsets. Stage B
    // centres another on the result to take the majority label.
    std::deque<Entry> a, b;
    size_t a_next = 0, b_next = 0;

    std::vector<FrameResult> ready;
    std::function<void(const FrameResult&, const cv::Mat&)>* hook = nullptr;

    void track_baseline(const FrameObservation& obs, Entry& e) {
        const double t = obs.t_s;
        while (!baseline.empty() && t - baseline.front().first > config.baseline_window_s) baseline.pop_front();
        while (!eye_seen.empty() && t - eye_seen.front().first > config.baseline_window_s) eye_seen.pop_front();

        double bh = 0.0, bv = 0.0;
        if (static_cast<int>(baseline.size()) >= config.baseline_min_frames) {
            std::vector<double> hs, vs;
            hs.reserve(baseline.size());
            vs.reserve(baseline.size());
            for (const auto& s : baseline) {
                hs.push_back(s.second.first);
                vs.push_back(s.second.second);
            }
            bh = median(std::move(hs));
            bv = median(std::move(vs));
        }
        e.h_rel = obs.h_offset - bh;
        e.v_rel = obs.v_offset - bv;
        if (static_cast<int>(eye_seen.size()) >= config.baseline_min_frames) {
            int found = 0;
            for (const auto& s : eye_seen) found += s.second;
            e.eyes_usual = found * 2 >= static_cast<int>(eye_seen.size());
        }
        if (single_frontal(obs)) {
            eye_seen.emplace_back(t, !obs.eyes.empty());
            if (obs.has_offsets) baseline.emplace_back(t, std::make_pair(obs.h_offset, obs.v_offset));
        }
    }

    void push_entry(Entry e) {
        a.push_back(std::move(e));
        drain_a(false);
    }

    void emit_a(size_t c) {
        Entry& e = a[c];
        const size_t lo = c >= static_cast<size_t>(k) ? c - k : 0;
        const size_t hi = std::min(a.size() - 1, c + k);
        std::vector<double> hs, vs;
        for (size_t i = lo; i <= hi; ++i) {
            if (single_frontal(a[i].obs) && a[i].obs.has_offsets) {
                hs.push_back(a[i].h_rel);
                vs.push_back(a[i].v_rel);
            }
        }
        e.h_med = hs.empty() ? e.h_rel : median(hs);
        e.v_med = vs.empty() ? e.v_rel : median(vs);
        e.pre = classify(e.obs, e.h_med, e.v_med, e.eyes_usual, config);
        b.push_back(e);
        drain_b(false);
    }

    void drain_a(bool all) {
        while (a_next < a.size() && (all || a_next + k < a.size())) emit_a(a_next++);
        while (a_next > static_cast<size_t>(k)) {
            a.pop_front();
            --a_next;
        }
    }

    void emit_b(size_t c) {
        const Entry& e = b[c];
        const size_t lo = c >= static_cast<size_t>(k) ? c - k : 0;
        const size_t hi = std::min(b.size() - 1, c + k);
        std::map<Label, int> votes;
        for (size_t i = lo; i <= hi; ++i) ++votes[b[i].pre.label];
        Label winner = e.pre.label;
        int best = votes[winner];
        for (const auto& [label, n] : votes) {
            if (n > best) {
                best = n;
                winner = label;
            }
        }
        FrameResult r;
        r.index = e.obs.index;
        r.t_s = e.obs.t_s;
        r.raw = e.raw.label;
        r.confidence = e.raw.confidence;
        r.label = winner;
        r.faces = static_cast<int>(e.obs.faces.size());
        r.eyes = static_cast<int>(e.obs.eyes.size());
        r.h_offset = e.h_med;
        r.v_offset = e.v_med;
        segmenter.push(r);
        if (hook && *hook) (*hook)(r, e.frame);
        ready.push_back(r);
    }

    void drain_b(bool all) {
        while (b_next < b.size() && (all || b_next + k < b.size())) emit_b(b_next++);
        while (b_next > static_cast<size_t>(k)) {
            b.pop_front();
            --b_next;
        }
    }
};

Session::Session(const Config& config, const std::string& cascade_dir)
    : config_(config), impl_(std::make_unique<Impl>(config, cascade_dir)) {
    impl_->hook = &on_final;
}

Session::~Session() = default;

std::vector<FrameResult> Session::push(const cv::Mat& input, double t_s) {
    cv::Mat bgr = input;
    if (config_.max_width > 0 && input.cols > config_.max_width) {
        const double s = static_cast<double>(config_.max_width) / input.cols;
        cv::resize(input, bgr, cv::Size(), s, s, cv::INTER_AREA);
    }
    Entry e;
    e.obs = impl_->detector.observe(bgr, t_s, next_index_++);
    impl_->track_baseline(e.obs, e);
    e.raw = classify(e.obs, e.h_rel, e.v_rel, e.eyes_usual, config_);
    if (on_final) e.frame = bgr.clone();
    impl_->push_entry(std::move(e));
    std::vector<FrameResult> out;
    out.swap(impl_->ready);
    return out;
}

std::vector<FrameResult> Session::push_bgr(const uint8_t* data, int width, int height, size_t stride,
                                           double t_s) {
    if (!data || width <= 0 || height <= 0) throw std::invalid_argument("zeg-gaze: empty frame");
    if (stride == 0) stride = static_cast<size_t>(width) * 3;
    // Wraps the caller's memory without copying; the detector only reads it.
    const cv::Mat view(height, width, CV_8UC3, const_cast<uint8_t*>(data), stride);
    return push(view, t_s);
}

std::vector<Flag> Session::take_closed() { return impl_->segmenter.take_closed(); }

std::vector<Flag> Session::finish() {
    impl_->drain_a(true);
    impl_->drain_b(true);
    impl_->ready.clear();
    return impl_->segmenter.finish();
}

// ---------------------------------------------------------------------------------

VideoSummary process_video(const std::string& path, const Config& config, const std::string& cascade_dir,
                           const std::string& sample_dir,
                           const std::function<void(const FrameResult&)>& per_frame) {
    cv::VideoCapture cap(path);
    if (!cap.isOpened()) throw std::runtime_error("zeg-gaze: cannot open video " + path);
    double fps = cap.get(cv::CAP_PROP_FPS);
    if (!(fps > 0.0 && fps < 1000.0)) fps = 30.0;

    Session session(config, cascade_dir);
    VideoSummary summary;
    std::vector<Flag> flags;
    cv::Mat frame;
    double analysis_s = 0.0;
    const auto started = std::chrono::steady_clock::now();
    int64_t index = 0;
    while (cap.read(frame)) {
        if (frame.empty()) break;
        if (summary.width == 0) {
            summary.width = frame.cols;
            summary.height = frame.rows;
        }
        const double t = index / fps;
        const auto a0 = std::chrono::steady_clock::now();
        auto done = session.push(frame, t);
        analysis_s += std::chrono::duration<double>(std::chrono::steady_clock::now() - a0).count();
        if (per_frame) for (const auto& r : done) per_frame(r);
        for (auto& f : session.take_closed()) flags.push_back(f);
        ++index;
    }
    {
        // finish() drains the last half-window; report those frames too.
        const auto a0 = std::chrono::steady_clock::now();
        std::vector<FrameResult> tail;
        auto keep = session.on_final;
        if (per_frame) {
            session.on_final = [&](const FrameResult& r, const cv::Mat&) { tail.push_back(r); };
        }
        for (auto& f : session.finish()) flags.push_back(f);
        session.on_final = keep;
        analysis_s += std::chrono::duration<double>(std::chrono::steady_clock::now() - a0).count();
        if (per_frame) for (const auto& r : tail) per_frame(r);
    }
    const double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count();
    summary.flags = merge_flags(std::move(flags), config.merge_gap_s);
    summary.frames = index;
    summary.duration_s = index / fps;
    summary.processing_fps = wall > 0 ? index / wall : 0.0;
    summary.analysis_fps = analysis_s > 0 ? index / analysis_s : 0.0;

    if (!sample_dir.empty() && !summary.flags.empty()) {
        // Second pass for the stills: which frames are wanted is known only at the end.
        std::map<int64_t, std::vector<Flag*>> wanted;
        for (Flag& f : summary.flags) wanted[f.sample_frame].push_back(&f);
        cv::VideoCapture again(path);
        int64_t i = 0;
        cv::Mat img;
        while (!wanted.empty() && again.grab()) {
            auto it = wanted.find(i);
            if (it != wanted.end() && again.retrieve(img)) {
                char name[64];
                std::snprintf(name, sizeof name, "/flag_%06lld.jpg", static_cast<long long>(i));
                const std::string out = sample_dir + name;
                if (cv::imwrite(out, img)) {
                    for (Flag* f : it->second) f->sample_image = out;
                }
                wanted.erase(it);
            }
            ++i;
        }
    }
    return summary;
}

}  // namespace zeg::gaze
