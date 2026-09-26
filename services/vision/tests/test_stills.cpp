// The whole pipeline on real face photographs (tests/fixtures/stills, public domain or
// CC0; sources in services/vision/eval/DATA.md). Each still is held for a second of
// frames so the smoothing and baseline run as they would on a call.
#include <gtest/gtest.h>

#include <map>
#include <string>
#include <vector>

#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>

#include "zeg_gaze/gaze.hpp"

using namespace zeg::gaze;

namespace {

const std::string kStills = std::string(ZEG_GAZE_FIXTURES) + "/stills";

std::vector<std::string> stills(const std::string& pattern) {
    std::vector<cv::String> found;
    cv::glob(kStills + "/" + pattern, found, false);
    return {found.begin(), found.end()};
}

// A webcam-shaped frame: the photo scaled to 480 tall on a plain 640x480 background.
cv::Mat webcam(const cv::Mat& photo, int dx = 0) {
    cv::Mat frame(480, 640, CV_8UC3, cv::Scalar(120, 130, 125));
    const double s = 480.0 / photo.rows;
    cv::Mat r;
    cv::resize(photo, r, cv::Size(), s, s, cv::INTER_AREA);
    const cv::Rect where(320 - r.cols / 2 + dx, 0, r.cols, r.rows);
    const cv::Rect clip = where & cv::Rect(0, 0, 640, 480);
    r(cv::Rect(clip.x - where.x, 0, clip.width, clip.height)).copyTo(frame(clip));
    return frame;
}

// The label the pipeline settles on for a frame held still for 1.5 s at 15 fps.
Label settle(const cv::Mat& frame) {
    Session session;
    std::map<Label, int> votes;
    for (int i = 0; i < 23; ++i) {
        for (const auto& r : session.push(frame, i / 15.0)) ++votes[r.label];
    }
    session.finish();
    Label best = Label::OnScreen;
    int n = -1;
    for (const auto& [label, count] : votes) {
        if (count > n) {
            n = count;
            best = label;
        }
    }
    return best;
}

}  // namespace

TEST(Stills, AFrontalFaceLookingAtTheCameraIsOnScreen) {
    const auto files = stills("frontal_*.jpg");
    if (files.empty()) GTEST_SKIP() << "no stills in " << kStills;
    for (const auto& f : files) {
        const cv::Mat photo = cv::imread(f);
        ASSERT_FALSE(photo.empty()) << f;
        EXPECT_EQ(settle(webcam(photo)), Label::OnScreen) << f;
        // Mirrored and shifted sideways: still a face looking at the camera.
        cv::Mat mirrored;
        cv::flip(photo, mirrored, 1);
        EXPECT_EQ(settle(webcam(mirrored, 60)), Label::OnScreen) << f << " mirrored";
    }
}

// profile_1 (a man in a patterned cap, turned a full 90 degrees, soft light) is a miss
// for OpenCV's profile cascade at every scale and neighbour setting tried: it reads as no
// face. It stays here as a pinned known failure, so a change that fixes it or breaks the
// other one shows up. docs/12-video-review.md, "What it does not handle well".
const char* const kKnownProfileMisses[] = {"profile_1.jpg"};

TEST(Stills, AHeadInProfileIsLookingAwayAndItsMirrorTheOtherWay) {
    const auto files = stills("profile_*.jpg");
    if (files.empty()) GTEST_SKIP() << "no stills in " << kStills;
    int detected = 0;
    for (const auto& f : files) {
        const cv::Mat photo = cv::imread(f);
        ASSERT_FALSE(photo.empty()) << f;
        cv::Mat mirrored;
        cv::flip(photo, mirrored, 1);
        const Label a = settle(webcam(photo)), b = settle(webcam(mirrored));
        bool known_miss = false;
        for (const char* name : kKnownProfileMisses) known_miss = known_miss || f.find(name) != std::string::npos;
        if (known_miss) {
            EXPECT_EQ(a, Label::NoFace) << f << " is a pinned miss and now reads as " << label_name(a);
            EXPECT_EQ(b, Label::NoFace) << f << " mirrored is a pinned miss and now reads as " << label_name(b);
            continue;
        }
        // All the profile stills face the image left: the candidate's own right.
        EXPECT_EQ(a, Label::AwayRight) << f << " read as " << label_name(a);
        EXPECT_EQ(b, Label::AwayLeft) << f << " mirrored read as " << label_name(b);
        ++detected;
    }
    EXPECT_GE(detected, 1);
}

TEST(Stills, AnEmptyRoomHasNoFace) {
    cv::Mat room(480, 640, CV_8UC3, cv::Scalar(120, 130, 125));
    cv::rectangle(room, cv::Rect(60, 200, 180, 200), cv::Scalar(60, 70, 90), cv::FILLED);
    EXPECT_EQ(settle(room), Label::NoFace);
}

TEST(Stills, TwoPeopleSideBySideAreMultipleFaces) {
    const auto files = stills("frontal_*.jpg");
    if (files.size() < 2) GTEST_SKIP() << "needs two frontal stills";
    cv::Mat frame(480, 640, CV_8UC3, cv::Scalar(120, 130, 125));
    for (int i = 0; i < 2; ++i) {
        const cv::Mat photo = cv::imread(files[i]);
        const double s = 340.0 / photo.rows;
        cv::Mat r;
        cv::resize(photo, r, cv::Size(), s, s, cv::INTER_AREA);
        const cv::Rect where(i == 0 ? 160 - r.cols / 2 : 480 - r.cols / 2, 140, r.cols, r.rows);
        const cv::Rect clip = where & cv::Rect(0, 0, 640, 480);
        r(cv::Rect(clip.x - where.x, clip.y - where.y, clip.width, clip.height)).copyTo(frame(clip));
    }
    EXPECT_EQ(settle(frame), Label::MultipleFaces);
}

TEST(Stills, RawBgrBuffersGiveTheSameAnswerAsMats) {
    const auto files = stills("frontal_*.jpg");
    if (files.empty()) GTEST_SKIP();
    const cv::Mat frame = webcam(cv::imread(files[0]));
    Session a, b;
    std::vector<Label> la, lb;
    for (int i = 0; i < 15; ++i) {
        for (const auto& r : a.push(frame, i / 15.0)) la.push_back(r.label);
        for (const auto& r : b.push_bgr(frame.data, frame.cols, frame.rows, frame.step, i / 15.0)) lb.push_back(r.label);
    }
    EXPECT_EQ(la, lb);
}
