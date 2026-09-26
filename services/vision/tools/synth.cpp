// zeg-gaze-synth: build labelled synthetic call clips from a few face stills.
//
//   zeg-gaze-synth --frontal a.jpg,b.jpg,c.jpg --profile p.jpg[,q.jpg] --out DIR
//                  [--clips 12] [--dev 4] [--seed 7] [--fps 15] [--seconds 45]
//
// Each clip is a random timeline of segments with exact ground truth:
//   on_screen       a frontal still, swaying, drifting in brightness, shifted around the frame
//   away_left/right a head-in-profile still (mirrored for the other side)
//   no_face         the subject out of frame: empty room, or only the shoulders showing
//   multiple_faces  two different frontal stills side by side
// Durations straddle the flag thresholds on purpose, so the eval sees spans that should
// not be flagged as well as ones that should. Profile stills must have the nose pointing
// to the image LEFT; the mirror gives the other side.
//
// Writes DIR/<id>.avi (MJPEG, readable by OpenCV without FFmpeg), DIR/labels.json with a
// label every 0.5 s, and DIR/clips.json. The first --dev clips are the tuning split.
#include <cmath>
#include <cstdio>
#include <fstream>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/videoio.hpp>

namespace {

const int W = 640, H = 480;

std::vector<std::string> split_csv(const std::string& s) {
    std::vector<std::string> out;
    std::stringstream ss(s);
    std::string item;
    while (std::getline(ss, item, ',')) if (!item.empty()) out.push_back(item);
    return out;
}

cv::Mat load(const std::string& path) {
    cv::Mat m = cv::imread(path, cv::IMREAD_COLOR);
    if (m.empty()) throw std::runtime_error("cannot read " + path);
    return m;
}

// A plain room: a vertical gradient wall, a floor band and a couple of shapes.
cv::Mat make_background(std::mt19937& rng) {
    std::uniform_int_distribution<int> c(60, 200);
    cv::Mat bg(H, W, CV_8UC3);
    const cv::Vec3b top(c(rng), c(rng), c(rng)), bottom(c(rng), c(rng), c(rng));
    for (int y = 0; y < H; ++y) {
        const double a = static_cast<double>(y) / H;
        const cv::Vec3b row(static_cast<uchar>(top[0] * (1 - a) + bottom[0] * a),
                            static_cast<uchar>(top[1] * (1 - a) + bottom[1] * a),
                            static_cast<uchar>(top[2] * (1 - a) + bottom[2] * a));
        bg.row(y).setTo(row);
    }
    std::uniform_int_distribution<int> px(0, W - 1), py(0, H - 1), sz(40, 160);
    for (int i = 0; i < 3; ++i) {
        const cv::Point p(px(rng), py(rng));
        cv::rectangle(bg, cv::Rect(p.x, p.y, sz(rng), sz(rng)), cv::Scalar(c(rng), c(rng), c(rng)), cv::FILLED);
    }
    cv::GaussianBlur(bg, bg, cv::Size(9, 9), 0);
    return bg;
}

// Paste `img` scaled to `height` pixels tall with its centre at (cx, cy); clipped.
void paste(cv::Mat& dst, const cv::Mat& img, int height, int cx, int cy) {
    const double s = static_cast<double>(height) / img.rows;
    cv::Mat r;
    cv::resize(img, r, cv::Size(), s, s, s < 1 ? cv::INTER_AREA : cv::INTER_LINEAR);
    const cv::Rect where(cx - r.cols / 2, cy - r.rows / 2, r.cols, r.rows);
    const cv::Rect clip = where & cv::Rect(0, 0, dst.cols, dst.rows);
    if (clip.area() <= 0) return;
    r(cv::Rect(clip.x - where.x, clip.y - where.y, clip.width, clip.height)).copyTo(dst(clip));
}

struct Segment {
    std::string label;
    double start, end;
    int variant;  // which still, or which kind of no-face
};

}  // namespace

int main(int argc, char** argv) {
    std::vector<std::string> frontal_paths, profile_paths;
    std::string out;
    int clips = 12, dev = 4, fps = 15;
    unsigned seed = 7;
    double seconds = 45.0;
    try {
        for (int i = 1; i < argc; ++i) {
            const std::string a = argv[i];
            auto next = [&]() -> std::string {
                if (i + 1 >= argc) throw std::runtime_error("missing value for " + a);
                return argv[++i];
            };
            if (a == "--frontal") frontal_paths = split_csv(next());
            else if (a == "--profile") profile_paths = split_csv(next());
            else if (a == "--out") out = next();
            else if (a == "--clips") clips = std::stoi(next());
            else if (a == "--dev") dev = std::stoi(next());
            else if (a == "--seed") seed = static_cast<unsigned>(std::stoul(next()));
            else if (a == "--fps") fps = std::stoi(next());
            else if (a == "--seconds") seconds = std::stod(next());
            else throw std::runtime_error("unknown option " + a);
        }
        if (frontal_paths.size() < 2 || profile_paths.empty() || out.empty()) {
            std::fprintf(stderr, "usage: zeg-gaze-synth --frontal a.jpg,b.jpg[,..] --profile p.jpg[,..] --out DIR\n");
            return 2;
        }
        std::vector<cv::Mat> frontal, profile_left, profile_right;
        for (const auto& p : frontal_paths) frontal.push_back(load(p));
        for (const auto& p : profile_paths) {
            cv::Mat m = load(p), f;
            cv::flip(m, f, 1);
            profile_left.push_back(m);   // nose to the image left: the candidate's right
            profile_right.push_back(f);  // nose to the image right: the candidate's left
        }

        std::ofstream labels(out + "/labels.json"), index(out + "/clips.json");
        if (!labels || !index) throw std::runtime_error("cannot write into " + out);
        labels << "{\n";
        index << "[\n";

        std::mt19937 rng(seed);
        for (int c = 0; c < clips; ++c) {
            char id[32];
            std::snprintf(id, sizeof id, "synth_%02d", c + 1);

            // Timeline. On-screen stretches separate the events; event lengths are drawn
            // either side of the thresholds (5 s away and no face, 2 s multiple faces).
            std::vector<Segment> timeline;
            std::uniform_real_distribution<double> on_len(3.0, 10.0), away_len(2.0, 10.0),
                none_len(2.0, 10.0), multi_len(0.8, 5.0);
            std::uniform_int_distribution<int> kind(0, 3), coin(0, 1);
            const int subject = c % static_cast<int>(frontal.size());
            double t = 0.0;
            bool on = true;
            while (t < seconds) {
                Segment s;
                s.start = t;
                if (on) {
                    s.label = "on_screen";
                    s.variant = subject;
                    s.end = t + on_len(rng);
                } else {
                    switch (kind(rng)) {
                        case 0: s.label = "away_left"; s.end = t + away_len(rng); break;
                        case 1: s.label = "away_right"; s.end = t + away_len(rng); break;
                        case 2: s.label = "no_face"; s.end = t + none_len(rng); break;
                        default: s.label = "multiple_faces"; s.end = t + multi_len(rng); break;
                    }
                    s.variant = coin(rng);
                }
                s.end = std::min(s.end, seconds);
                timeline.push_back(s);
                t = s.end;
                on = !on;
            }

            const cv::Mat bg = make_background(rng);
            std::uniform_real_distribution<double> scale_d(0.85, 1.05), phase_d(0.0, 6.28);
            const double scale = scale_d(rng), phase = phase_d(rng);
            const int other = (subject + 1) % static_cast<int>(frontal.size());
            const std::string path = out + "/" + id + ".avi";
            cv::VideoWriter writer(path, cv::CAP_OPENCV_MJPEG, cv::VideoWriter::fourcc('M', 'J', 'P', 'G'),
                                   fps, cv::Size(W, H));
            if (!writer.isOpened()) throw std::runtime_error("cannot write " + path);
            const int frames = static_cast<int>(std::round(seconds * fps));
            size_t seg = 0;
            for (int f = 0; f < frames; ++f) {
                const double tt = static_cast<double>(f) / fps;
                while (seg + 1 < timeline.size() && tt >= timeline[seg].end) ++seg;
                const Segment& s = timeline[seg];
                cv::Mat frame = bg.clone();
                // Sway and a slow wander around the frame, so the face is not pinned.
                const int sway_x = static_cast<int>(18 * std::sin(0.9 * tt + phase) + 40 * std::sin(0.13 * tt));
                const int sway_y = static_cast<int>(8 * std::sin(0.7 * tt + 2 * phase));
                const int h = static_cast<int>(H * scale * (1.0 + 0.03 * std::sin(0.5 * tt)));
                if (s.label == "on_screen") {
                    paste(frame, frontal[s.variant], h, W / 2 + sway_x, H / 2 + sway_y + 20);
                } else if (s.label == "away_left") {
                    const auto& imgs = profile_right;
                    paste(frame, imgs[s.variant % imgs.size()], h, W / 2 + sway_x, H / 2 + sway_y + 20);
                } else if (s.label == "away_right") {
                    const auto& imgs = profile_left;
                    paste(frame, imgs[s.variant % imgs.size()], h, W / 2 + sway_x, H / 2 + sway_y + 20);
                } else if (s.label == "no_face") {
                    // Variant 1: the candidate has stood up; only the lower body shows.
                    if (s.variant == 1) paste(frame, frontal[subject], h, W / 2 + sway_x, H / 2 + h * 3 / 4);
                } else {
                    const int hh = static_cast<int>(h * 0.72);
                    paste(frame, frontal[subject], hh, W / 4 + sway_x / 2, H / 2 + 50 + sway_y);
                    paste(frame, frontal[other], hh, 3 * W / 4 + sway_x / 2, H / 2 + 50);
                }
                const double gain = 1.0 + 0.12 * std::sin(0.21 * tt + phase);
                frame.convertTo(frame, -1, gain, 0);
                cv::Mat n(frame.size(), CV_16SC3);
                cv::randn(n, 0, 4);
                cv::Mat f16;
                frame.convertTo(f16, CV_16SC3);
                f16 += n;
                f16.convertTo(frame, CV_8UC3);
                writer.write(frame);
            }
            writer.release();

            labels << "  \"" << id << "\": {\"step_s\": 0.5, \"synthetic\": true, \"samples\": [";
            seg = 0;
            bool first = true;
            for (double st = 0.0; st < seconds - 1e-9; st += 0.5) {
                while (seg + 1 < timeline.size() && st >= timeline[seg].end) ++seg;
                labels << (first ? "" : ", ") << "[" << st << ", \"" << timeline[seg].label << "\"]";
                first = false;
            }
            labels << "]}" << (c + 1 < clips ? "," : "") << "\n";
            index << "  {\"id\": \"" << id << "\", \"split\": \"" << (c < dev ? "dev" : "test")
                  << "\", \"synthetic\": true, \"fps\": " << fps << ", \"seconds\": " << seconds
                  << ", \"seed\": " << seed << "}" << (c + 1 < clips ? "," : "") << "\n";
            std::fprintf(stderr, "%s: %zu segments\n", id, timeline.size());
        }
        labels << "}\n";
        index << "]\n";
    } catch (const std::exception& e) {
        std::fprintf(stderr, "zeg-gaze-synth: %s\n", e.what());
        return 1;
    }
    return 0;
}
