// Face and eye detection with Haar cascades, and pupil localisation inside each eye.
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <stdexcept>

#include <opencv2/imgproc.hpp>

#include "zeg_gaze/gaze.hpp"

#ifndef ZEG_GAZE_DEFAULT_CASCADES
#define ZEG_GAZE_DEFAULT_CASCADES ""
#endif

namespace zeg::gaze {

namespace {

double iou(const cv::Rect& a, const cv::Rect& b) {
    const double inter = (a & b).area();
    const double uni = a.area() + b.area() - inter;
    return uni > 0 ? inter / uni : 0.0;
}

cv::Rect scale_rect(const cv::Rect& r, double s, const cv::Size& bounds) {
    cv::Rect out(cvRound(r.x * s), cvRound(r.y * s), cvRound(r.width * s), cvRound(r.height * s));
    return out & cv::Rect(0, 0, bounds.width, bounds.height);
}

void load(cv::CascadeClassifier& c, const std::string& dir, const char* name, bool required) {
    const std::string path = dir + "/" + name;
    if (!c.load(path) && required) {
        throw std::runtime_error("zeg-gaze: cannot load cascade " + path +
                                 " (set ZEG_GAZE_CASCADES or pass --cascades)");
    }
}

int odd(int k) { return k % 2 == 0 ? k + 1 : k; }

}  // namespace

std::string default_cascade_dir() {
    if (const char* env = std::getenv("ZEG_GAZE_CASCADES"); env && *env) return env;
    return ZEG_GAZE_DEFAULT_CASCADES;
}

// The pupil is the darkest compact blob in the eye. Equalise, keep the darkest few
// percent of pixels, take the connected component that is largest and least stuck to
// the patch border (brows, lashes and shadow tend to touch it), then its darkness
// weighted centroid.
std::optional<cv::Point2d> locate_pupil(const cv::Mat& eye_gray) {
    if (eye_gray.empty() || eye_gray.cols < 8 || eye_gray.rows < 6) return std::nullopt;
    cv::Mat p;
    const int k = odd(std::max(3, eye_gray.cols / 12));
    cv::GaussianBlur(eye_gray, p, cv::Size(k, k), 0);
    double lo = 0.0, hi = 0.0;
    cv::minMaxLoc(p, &lo, &hi);
    if (hi - lo < 20.0) return std::nullopt;  // flat patch: nothing dark stands out
    cv::normalize(p, p, 0, 255, cv::NORM_MINMAX);

    // Darkest ~10% of the patch.
    int hist[256] = {0};
    for (int y = 0; y < p.rows; ++y) {
        const uint8_t* row = p.ptr<uint8_t>(y);
        for (int x = 0; x < p.cols; ++x) ++hist[row[x]];
    }
    const int total = p.rows * p.cols;
    int cut = 0, acc = 0;
    for (; cut < 256; ++cut) {
        acc += hist[cut];
        if (acc >= total / 10) break;
    }
    cv::Mat mask = p <= cut;
    cv::morphologyEx(mask, mask, cv::MORPH_OPEN,
                     cv::getStructuringElement(cv::MORPH_ELLIPSE, cv::Size(3, 3)));

    cv::Mat labels, stats, centroids;
    const int n = cv::connectedComponentsWithStats(mask, labels, stats, centroids, 8, CV_32S);
    int best = -1;
    double best_score = 0.0;
    const double cx = p.cols / 2.0, cy = p.rows / 2.0;
    for (int i = 1; i < n; ++i) {
        const int area = stats.at<int>(i, cv::CC_STAT_AREA);
        if (area < std::max(4, total / 200)) continue;
        const int x = stats.at<int>(i, cv::CC_STAT_LEFT), y = stats.at<int>(i, cv::CC_STAT_TOP);
        const int w = stats.at<int>(i, cv::CC_STAT_WIDTH), h = stats.at<int>(i, cv::CC_STAT_HEIGHT);
        const int borders = (x == 0) + (y == 0) + (x + w >= p.cols) + (y + h >= p.rows);
        if (borders >= 3) continue;  // a band of shadow, not a pupil
        const double ddx = (centroids.at<double>(i, 0) - cx) / p.cols;
        const double ddy = (centroids.at<double>(i, 1) - cy) / p.rows;
        const double central = 1.0 - std::min(0.8, std::sqrt(ddx * ddx + ddy * ddy));
        const double score = area * central / (1.0 + 1.5 * borders);
        if (score > best_score) {
            best_score = score;
            best = i;
        }
    }
    if (best < 0) return std::nullopt;

    double sw = 0.0, sx = 0.0, sy = 0.0;
    for (int y = 0; y < p.rows; ++y) {
        const int* lab = labels.ptr<int>(y);
        const uint8_t* row = p.ptr<uint8_t>(y);
        for (int x = 0; x < p.cols; ++x) {
            if (lab[x] != best) continue;
            const double w = cut + 1.0 - row[x];
            sw += w;
            sx += w * x;
            sy += w * y;
        }
    }
    if (sw <= 0.0) return std::nullopt;
    return cv::Point2d(sx / sw, sy / sw);
}

Detector::Detector(const Config& config, const std::string& cascade_dir) : config_(config) {
    const std::string dir = cascade_dir.empty() ? default_cascade_dir() : cascade_dir;
    load(frontal_, dir, "haarcascade_frontalface_default.xml", true);
    load(profile_, dir, "haarcascade_profileface.xml", true);
    load(eye_, dir, "haarcascade_eye.xml", true);
    load(eye_glasses_, dir, "haarcascade_eye_tree_eyeglasses.xml", false);
}

std::vector<EyeResult> Detector::find_eyes(const cv::Mat& gray, const cv::Rect& face) const {
    std::vector<EyeResult> out;
    // Eyes sit in a band from about a fifth to a bit over half way down the face box.
    const int top = face.y + cvRound(face.height * 0.18);
    const int bottom = face.y + cvRound(face.height * 0.58);
    const int mid = face.x + face.width / 2;
    const cv::Rect halves[2] = {
        cv::Rect(cv::Point(face.x, top), cv::Point(mid, bottom)),
        cv::Rect(cv::Point(mid, top), cv::Point(face.x + face.width, bottom)),
    };
    const cv::Rect frame(0, 0, gray.cols, gray.rows);
    const int min_eye = std::max(8, cvRound(face.width * 0.12));
    const int max_eye = std::max(min_eye + 1, cvRound(face.width * 0.45));
    for (const cv::Rect& raw_half : halves) {
        const cv::Rect half = raw_half & frame;
        if (half.width < min_eye || half.height < min_eye) continue;
        cv::Mat roi;
        cv::equalizeHist(gray(half), roi);
        std::vector<cv::Rect> found;
        eye_.detectMultiScale(roi, found, 1.1, 3, 0, cv::Size(min_eye, min_eye),
                              cv::Size(max_eye, max_eye));
        if (found.empty() && !eye_glasses_.empty()) {
            eye_glasses_.detectMultiScale(roi, found, 1.1, 3, 0, cv::Size(min_eye, min_eye),
                                          cv::Size(max_eye, max_eye));
        }
        if (found.empty()) continue;
        const cv::Rect best = *std::max_element(found.begin(), found.end(),
            [](const cv::Rect& a, const cv::Rect& b) { return a.area() < b.area(); });

        EyeResult eye;
        eye.box = best + half.tl();
        // Drop the brow at the top and the lid shadow at the bottom of the Haar box.
        const cv::Rect inner(eye.box.x, eye.box.y + eye.box.height / 4, eye.box.width,
                             eye.box.height * 3 / 5);
        const cv::Rect clipped = inner & frame;
        if (clipped.area() > 0) {
            if (auto pupil = locate_pupil(gray(clipped))) {
                eye.pupil_found = true;
                eye.pupil = cv::Point2d(pupil->x + clipped.x, pupil->y + clipped.y);
                eye.dx = (pupil->x - clipped.width / 2.0) / clipped.width;
                eye.dy = (pupil->y - clipped.height / 2.0) / clipped.height;
            }
        }
        out.push_back(eye);
    }
    std::sort(out.begin(), out.end(),
              [](const EyeResult& a, const EyeResult& b) { return a.box.x < b.box.x; });
    return out;
}

bool Detector::has_an_eye(const cv::Mat& gray, const cv::Rect& face) const {
    const cv::Rect band = cv::Rect(face.x, face.y + face.height / 6, face.width, face.height / 2) &
                          cv::Rect(0, 0, gray.cols, gray.rows);
    const int min_eye = std::max(6, cvRound(face.width * 0.12));
    if (band.width < min_eye || band.height < min_eye) return false;
    cv::Mat roi;
    cv::equalizeHist(gray(band), roi);
    std::vector<cv::Rect> found;
    eye_.detectMultiScale(roi, found, 1.1, 3, 0, cv::Size(min_eye, min_eye));
    if (found.empty() && !eye_glasses_.empty()) {
        eye_glasses_.detectMultiScale(roi, found, 1.1, 3, 0, cv::Size(min_eye, min_eye));
    }
    return !found.empty();
}

FrameObservation Detector::observe(const cv::Mat& bgr, double t_s, int64_t index) const {
    FrameObservation obs;
    obs.index = index;
    obs.t_s = t_s;
    if (bgr.empty()) return obs;

    cv::Mat gray;
    if (bgr.channels() == 3) cv::cvtColor(bgr, gray, cv::COLOR_BGR2GRAY);
    else if (bgr.channels() == 4) cv::cvtColor(bgr, gray, cv::COLOR_BGRA2GRAY);
    else gray = bgr;

    const double down = gray.cols > config_.detect_width
                            ? static_cast<double>(config_.detect_width) / gray.cols : 1.0;
    cv::Mat small;
    if (down < 1.0) cv::resize(gray, small, cv::Size(), down, down, cv::INTER_AREA);
    else small = gray;
    cv::equalizeHist(small, small);

    const int min_face = std::max(20, cvRound(config_.min_face_fraction * small.cols));
    std::vector<cv::Rect> frontal;
    frontal_.detectMultiScale(small, frontal, config_.face_scale_factor,
                              config_.face_min_neighbors, 0, cv::Size(min_face, min_face));
    std::sort(frontal.begin(), frontal.end(),
              [](const cv::Rect& a, const cv::Rect& b) { return a.area() > b.area(); });

    const cv::Size full = gray.size();
    for (size_t i = 0; i < frontal.size(); ++i) {
        FaceResult f;
        f.box = scale_rect(frontal[i], 1.0 / down, full);
        // A second face has to show an eye before it counts: patterned shirts, flags
        // and shelves otherwise pass the frontal cascade often enough to read as a
        // second person. The largest face is the candidate and is not checked.
        if (i > 0 && !has_an_eye(gray, f.box)) continue;
        // Two windows on one face that the cascade's own grouping left apart.
        bool same = false;
        for (const FaceResult& kept : obs.faces) {
            const cv::Point c(f.box.x + f.box.width / 2, f.box.y + f.box.height / 2);
            same = same || iou(kept.box, f.box) > 0.3 || kept.box.contains(c);
        }
        if (same) continue;
        obs.faces.push_back(f);
    }

    if (obs.faces.empty()) {
        // No frontal face: is it a head turned away? The profile cascade is trained on
        // one orientation, so search the mirror image for the other.
        std::vector<cv::Rect> as_is, mirrored;
        profile_.detectMultiScale(small, as_is, config_.profile_scale_factor,
                                  config_.profile_min_neighbors, 0, cv::Size(min_face, min_face));
        cv::Mat flipped;
        cv::flip(small, flipped, 1);
        profile_.detectMultiScale(flipped, mirrored, config_.profile_scale_factor,
                                  config_.profile_min_neighbors, 0, cv::Size(min_face, min_face));
        std::vector<FaceResult> profiles;
        // OpenCV's profile cascade finds faces whose nose points to the image left.
        for (const cv::Rect& r : as_is) {
            FaceResult f;
            f.box = scale_rect(r, 1.0 / down, full);
            f.profile = true;
            f.facing_image_right = false;
            profiles.push_back(f);
        }
        for (const cv::Rect& r : mirrored) {
            FaceResult f;
            const cv::Rect back(small.cols - r.x - r.width, r.y, r.width, r.height);
            f.box = scale_rect(back, 1.0 / down, full);
            f.profile = true;
            f.facing_image_right = true;
            profiles.push_back(f);
        }
        std::sort(profiles.begin(), profiles.end(), [](const FaceResult& a, const FaceResult& b) {
            return a.box.area() > b.box.area();
        });
        for (const FaceResult& f : profiles) {
            bool dup = false;
            for (const FaceResult& kept : obs.faces) dup = dup || iou(kept.box, f.box) > 0.3;
            if (!dup) obs.faces.push_back(f);
        }
        return obs;
    }

    // One or more frontal faces: the largest is the candidate. Read their eyes.
    const cv::Rect& face = obs.faces.front().box;
    obs.eyes = find_eyes(gray, face);
    double sum_dx = 0.0, sum_dy = 0.0;
    int pupils = 0;
    for (const EyeResult& e : obs.eyes) {
        if (!e.pupil_found) continue;
        sum_dx += e.dx;
        sum_dy += e.dy;
        ++pupils;
    }
    if (obs.eyes.size() == 2) {
        const double mid_x = (obs.eyes[0].box.x + obs.eyes[0].box.width / 2.0 +
                              obs.eyes[1].box.x + obs.eyes[1].box.width / 2.0) / 2.0;
        obs.yaw = (mid_x - (face.x + face.width / 2.0)) / face.width;
    }
    if (pupils > 0 || obs.eyes.size() == 2) {
        obs.has_offsets = true;
        const double pupil_dx = pupils ? sum_dx / pupils : 0.0;
        obs.h_offset = pupil_dx + config_.yaw_weight * obs.yaw;
        obs.v_offset = pupils ? sum_dy / pupils : 0.0;
    }
    return obs;
}

}  // namespace zeg::gaze
