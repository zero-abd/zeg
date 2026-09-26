// zeg-gaze-inspect: what the detector sees in one image, drawn on it.
//
//   zeg-gaze-inspect photo.jpg [--out annotated.jpg] [--mirror]
//
// Prints the faces (frontal or profile, and which way a profile faces), the eyes, the
// pupil offsets and the label a single frame would get, and writes the image with the
// boxes and pupils drawn. For learning how the pieces behave and for debugging a miss.
#include <cstdio>
#include <string>

#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>

#include "zeg_gaze/gaze.hpp"

using namespace zeg::gaze;

int main(int argc, char** argv) {
    std::string in, out;
    bool mirror = false;
    for (int i = 1; i < argc; ++i) {
        const std::string a = argv[i];
        if (a == "--out" && i + 1 < argc) out = argv[++i];
        else if (a == "--mirror") mirror = true;
        else in = a;
    }
    if (in.empty()) {
        std::fprintf(stderr, "usage: zeg-gaze-inspect image [--out annotated.jpg] [--mirror]\n");
        return 2;
    }
    cv::Mat img = cv::imread(in, cv::IMREAD_COLOR);
    if (img.empty()) {
        std::fprintf(stderr, "cannot read %s\n", in.c_str());
        return 1;
    }
    if (mirror) cv::flip(img, img, 1);
    const Config config;
    if (img.cols > config.max_width) {
        const double s = static_cast<double>(config.max_width) / img.cols;
        cv::resize(img, img, cv::Size(), s, s, cv::INTER_AREA);
    }
    const Detector detector(config);
    const FrameObservation obs = detector.observe(img, 0.0, 0);
    std::printf("%s %dx%d: %zu face(s)\n", in.c_str(), img.cols, img.rows, obs.faces.size());
    for (const FaceResult& f : obs.faces) {
        std::printf("  face %d,%d %dx%d %s\n", f.box.x, f.box.y, f.box.width, f.box.height,
                    f.profile ? (f.facing_image_right ? "profile, nose to image right" : "profile, nose to image left")
                              : "frontal");
        cv::rectangle(img, f.box, f.profile ? cv::Scalar(0, 165, 255) : cv::Scalar(0, 255, 0), 2);
    }
    for (const EyeResult& e : obs.eyes) {
        std::printf("  eye %d,%d %dx%d pupil %s dx %+.3f dy %+.3f\n", e.box.x, e.box.y, e.box.width, e.box.height,
                    e.pupil_found ? "found" : "missing", e.dx, e.dy);
        cv::rectangle(img, e.box, cv::Scalar(255, 200, 0), 1);
        if (e.pupil_found) cv::circle(img, e.pupil, 2, cv::Scalar(0, 0, 255), cv::FILLED);
    }
    const Classification c = classify(obs, obs.h_offset, obs.v_offset, true, config);
    std::printf("  yaw %+.3f  horizontal %+.3f  vertical %+.3f  ->  %s (%.2f)\n", obs.yaw, obs.h_offset,
                obs.v_offset, label_name(c.label), c.confidence);
    if (!out.empty()) cv::imwrite(out, img);
    return 0;
}
