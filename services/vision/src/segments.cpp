// Labels, per-frame classification, and turning labelled frames into flagged spans.
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <sstream>

#include "zeg_gaze/gaze.hpp"

namespace zeg::gaze {

const char* label_name(Label label) {
    switch (label) {
        case Label::OnScreen: return "on_screen";
        case Label::AwayLeft: return "away_left";
        case Label::AwayRight: return "away_right";
        case Label::AwayDown: return "away_down";
        case Label::NoFace: return "no_face";
        case Label::MultipleFaces: return "multiple_faces";
    }
    return "unknown";
}

std::optional<Label> label_from_name(const std::string& name) {
    for (int i = 0; i <= static_cast<int>(Label::MultipleFaces); ++i) {
        const Label l = static_cast<Label>(i);
        if (name == label_name(l)) return l;
    }
    return std::nullopt;
}

bool is_away(Label label) {
    return label == Label::AwayLeft || label == Label::AwayRight || label == Label::AwayDown;
}

const char* reason_name(Reason reason) {
    switch (reason) {
        case Reason::LookingAway: return "looking_away";
        case Reason::NoFace: return "no_face";
        case Reason::MultipleFaces: return "multiple_faces";
    }
    return "unknown";
}

std::optional<Reason> reason_for(Label label) {
    if (is_away(label)) return Reason::LookingAway;
    if (label == Label::NoFace) return Reason::NoFace;
    if (label == Label::MultipleFaces) return Reason::MultipleFaces;
    return std::nullopt;
}

namespace {
double clamp01(double x) { return std::max(0.0, std::min(1.0, x)); }
}  // namespace

Classification classify(const FrameObservation& obs, double h_rel, double v_rel,
                        bool eyes_usually_found, const Config& config) {
    if (obs.faces.size() >= 2) return {Label::MultipleFaces, 0.9};
    if (obs.faces.empty()) return {Label::NoFace, 0.8};
    const FaceResult& face = obs.faces.front();
    if (face.profile) {
        // Nose toward the image right is the candidate turning to their own left.
        return {face.facing_image_right ? Label::AwayLeft : Label::AwayRight, 0.8};
    }
    if (!obs.has_offsets) {
        // A frontal face whose eyes cannot be found. For someone whose eyes are normally
        // found, that is lids lowered: looking down, or eyes closed. For someone whose
        // eyes are rarely found (glasses glare, low light), it says nothing.
        if (eyes_usually_found) return {Label::AwayDown, 0.5};
        return {Label::OnScreen, 0.4};
    }
    const double ht = config.horizontal_threshold, vt = config.down_threshold;
    if (std::fabs(h_rel) > ht) {
        return {h_rel > 0 ? Label::AwayLeft : Label::AwayRight,
                clamp01(0.5 + 0.5 * (std::fabs(h_rel) - ht) / ht)};
    }
    if (v_rel > vt) return {Label::AwayDown, clamp01(0.5 + 0.5 * (v_rel - vt) / vt)};
    const double margin = std::min((ht - std::fabs(h_rel)) / ht, (vt - std::max(0.0, v_rel)) / vt);
    return {Label::OnScreen, clamp01(0.5 + 0.5 * margin)};
}

// ---------------------------------------------------------------------------------

Segmenter::Segmenter(const Config& config) : config_(config) {}

double Segmenter::threshold_for(Reason reason) const {
    switch (reason) {
        case Reason::LookingAway: return config_.away_threshold_s;
        case Reason::NoFace: return config_.no_face_threshold_s;
        case Reason::MultipleFaces: return config_.multi_face_threshold_s;
    }
    return config_.away_threshold_s;
}

void Segmenter::push(const FrameResult& frame) {
    if (last_t_ >= 0.0) {
        const double step = frame.t_s - last_t_;
        if (step > 0.0) dt_ = dt_ > 0.0 ? 0.9 * dt_ + 0.1 * step : step;
    }
    last_t_ = frame.t_s;

    const auto mine = reason_for(frame.label);
    for (int r = 0; r < 3; ++r) {
        Run& run = runs_[r];
        if (mine && static_cast<int>(*mine) == r) {
            if (!run.open) {
                run = Run();
                run.open = true;
                run.start_s = frame.t_s;
            }
            run.last_s = frame.t_s;
            run.frames.push_back(frame);
        } else if (run.open) {
            if (frame.t_s - run.last_s > config_.max_gap_s) {
                // Trim the gap frames that were kept in case the run resumed.
                while (!run.frames.empty() && run.frames.back().t_s > run.last_s) run.frames.pop_back();
                close_run(r, run.last_s + dt_);
            } else {
                run.frames.push_back(frame);  // inside a tolerated gap
            }
        }
    }
    release(false, frame.t_s);
}

void Segmenter::close_run(int r, double end_s) {
    Run& run = runs_[r];
    const Reason reason = static_cast<Reason>(r);
    const double duration = end_s - run.start_s;
    if (run.open && duration >= threshold_for(reason) && !run.frames.empty()) {
        Flag flag;
        flag.start_s = run.start_s;
        flag.end_s = end_s;
        flag.reason = reason;
        double agree = 0.0;
        int left = 0, right = 0, down = 0;
        for (const FrameResult& f : run.frames) {
            if (reason_for(f.raw) == reason) agree += f.confidence;
            left += f.label == Label::AwayLeft;
            right += f.label == Label::AwayRight;
            down += f.label == Label::AwayDown;
        }
        flag.confidence = agree / run.frames.size();
        if (reason == Reason::LookingAway) {
            const int n = left + right + down;
            const int top = std::max({left, right, down});
            if (n == 0 || top < 0.6 * n) flag.direction = "mixed";
            else if (top == left) flag.direction = "left";
            else if (top == right) flag.direction = "right";
            else flag.direction = "down";
        }
        // The middle frame that carries the flagged label, as the still to look at.
        const double mid_t = (flag.start_s + flag.end_s) / 2.0;
        const FrameResult* best = nullptr;
        for (const FrameResult& f : run.frames) {
            if (reason_for(f.label) != reason) continue;
            if (!best || std::fabs(f.t_s - mid_t) < std::fabs(best->t_s - mid_t)) best = &f;
        }
        if (!best) best = &run.frames[run.frames.size() / 2];
        flag.sample_frame = best->index;
        flag.sample_t_s = best->t_s;
        closed_.push_back(flag);
    }
    run = Run();
}

std::vector<Flag> merge_flags(std::vector<Flag> flags, double gap_s) {
    std::sort(flags.begin(), flags.end(), [](const Flag& a, const Flag& b) {
        return a.start_s < b.start_s || (a.start_s == b.start_s && a.reason < b.reason);
    });
    std::vector<Flag> out;
    for (const Flag& f : flags) {
        Flag* prev = nullptr;
        for (auto it = out.rbegin(); it != out.rend(); ++it) {
            if (it->reason == f.reason) {
                prev = &*it;
                break;
            }
        }
        if (prev && f.start_s - prev->end_s < gap_s) {
            const double a = prev->end_s - prev->start_s, b = f.end_s - f.start_s;
            prev->confidence = (prev->confidence * a + f.confidence * b) / std::max(1e-9, a + b);
            if (prev->direction != f.direction) prev->direction = "mixed";
            if (b > a) {
                prev->sample_frame = f.sample_frame;
                prev->sample_t_s = f.sample_t_s;
                prev->sample_image = f.sample_image;
            }
            prev->end_s = std::max(prev->end_s, f.end_s);
        } else {
            out.push_back(f);
        }
    }
    std::sort(out.begin(), out.end(), [](const Flag& a, const Flag& b) { return a.start_s < b.start_s; });
    return out;
}

void Segmenter::release(bool all, double now_s) {
    if (closed_.empty()) return;
    closed_ = merge_flags(std::move(closed_), config_.merge_gap_s);
    std::vector<Flag> keep;
    for (const Flag& f : closed_) {
        const Run& run = runs_[static_cast<int>(f.reason)];
        // Held back while a later span of the same reason could still merge into it.
        const bool settled = now_s - f.end_s >= config_.merge_gap_s &&
                             (!run.open || run.start_s - f.end_s >= config_.merge_gap_s);
        if (all || settled) ready_.push_back(f);
        else keep.push_back(f);
    }
    closed_ = std::move(keep);
}

std::vector<Flag> Segmenter::take_closed() {
    std::vector<Flag> out;
    out.swap(ready_);
    return out;
}

std::vector<Flag> Segmenter::finish() {
    for (int r = 0; r < 3; ++r) {
        if (runs_[r].open) {
            Run& run = runs_[r];
            while (!run.frames.empty() && run.frames.back().t_s > run.last_s) run.frames.pop_back();
            close_run(r, run.last_s + dt_);
        }
    }
    release(true, last_t_);
    auto out = take_closed();
    return merge_flags(std::move(out), config_.merge_gap_s);
}

// ---------------------------------------------------------------------------------

namespace {
std::string escape(const std::string& s) {
    std::string out;
    for (char c : s) {
        switch (c) {
            case '"': out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\n': out += "\\n"; break;
            default:
                if (static_cast<unsigned char>(c) < 0x20) {
                    char buf[8];
                    std::snprintf(buf, sizeof buf, "\\u%04x", c);
                    out += buf;
                } else {
                    out += c;
                }
        }
    }
    return out;
}

std::string num(double x, int places) {
    char buf[32];
    std::snprintf(buf, sizeof buf, "%.*f", places, x);
    return buf;
}
}  // namespace

std::string flags_to_json(const std::vector<Flag>& flags, int indent) {
    const std::string pad(indent, ' '), pad2(indent * 2, ' ');
    const char* nl = indent > 0 ? "\n" : "";
    const char* sp = indent > 0 ? " " : "";
    std::ostringstream os;
    os << "[" << (flags.empty() ? "" : nl);
    for (size_t i = 0; i < flags.size(); ++i) {
        const Flag& f = flags[i];
        os << pad << "{" << nl;
        os << pad2 << "\"start_s\":" << sp << num(f.start_s, 2) << "," << nl;
        os << pad2 << "\"end_s\":" << sp << num(f.end_s, 2) << "," << nl;
        os << pad2 << "\"reason\":" << sp << "\"" << reason_name(f.reason) << "\"," << nl;
        if (!f.direction.empty()) {
            os << pad2 << "\"direction\":" << sp << "\"" << escape(f.direction) << "\"," << nl;
        }
        os << pad2 << "\"confidence\":" << sp << num(f.confidence, 2) << "," << nl;
        os << pad2 << "\"sample_frame\":" << sp << f.sample_frame << "," << nl;
        os << pad2 << "\"sample_t_s\":" << sp << num(f.sample_t_s, 2);
        if (!f.sample_image.empty()) {
            os << "," << nl << pad2 << "\"sample_image\":" << sp << "\"" << escape(f.sample_image) << "\"";
        }
        os << nl << pad << "}" << (i + 1 < flags.size() ? "," : "") << nl;
    }
    os << "]";
    return os.str();
}

}  // namespace zeg::gaze
