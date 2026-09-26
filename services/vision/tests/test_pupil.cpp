// The pupil finder on drawn eyes, where the right answer is known to the pixel.
#include <gtest/gtest.h>

#include <opencv2/imgproc.hpp>

#include "zeg_gaze/gaze.hpp"

using namespace zeg::gaze;

namespace {

// Skin, a white almond of sclera, a grey-brown iris and a black pupil at (px, py).
cv::Mat drawn_eye(int px, int py, int w = 60, int h = 36) {
    cv::Mat eye(h, w, CV_8UC1, cv::Scalar(165));
    cv::ellipse(eye, cv::Point(w / 2, h / 2), cv::Size(w * 2 / 5, h / 3), 0, 0, 360, cv::Scalar(225), cv::FILLED);
    cv::Mat iris(h, w, CV_8UC1, cv::Scalar(0));
    cv::circle(iris, cv::Point(px, py), h / 4, cv::Scalar(255), cv::FILLED);
    cv::Mat almond(h, w, CV_8UC1, cv::Scalar(0));
    cv::ellipse(almond, cv::Point(w / 2, h / 2), cv::Size(w * 2 / 5, h / 3), 0, 0, 360, cv::Scalar(255), cv::FILLED);
    cv::bitwise_and(iris, almond, iris);
    eye.setTo(cv::Scalar(90), iris);
    cv::circle(eye, cv::Point(px, py), h / 9, cv::Scalar(25), cv::FILLED);
    return eye;
}

}  // namespace

TEST(Pupil, FindsACentredPupil) {
    auto p = locate_pupil(drawn_eye(30, 18));
    ASSERT_TRUE(p.has_value());
    EXPECT_NEAR(p->x, 30, 2.0);
    EXPECT_NEAR(p->y, 18, 2.0);
}

TEST(Pupil, FollowsThePupilLeftAndRight) {
    for (int px : {20, 25, 35, 40}) {
        auto p = locate_pupil(drawn_eye(px, 18));
        ASSERT_TRUE(p.has_value()) << "pupil at x=" << px;
        EXPECT_NEAR(p->x, px, 2.5) << "pupil at x=" << px;
    }
}

TEST(Pupil, SurvivesNoiseAndDimLight) {
    cv::Mat eye = drawn_eye(38, 18);
    cv::Mat noise(eye.size(), CV_8UC1);
    cv::randn(noise, 0, 8);
    cv::Mat dim;
    eye.convertTo(dim, -1, 0.45, 10);  // underexposed webcam
    dim += noise;
    auto p = locate_pupil(dim);
    ASSERT_TRUE(p.has_value());
    EXPECT_NEAR(p->x, 38, 3.0);
}

TEST(Pupil, AFlatPatchHasNoPupil) {
    cv::Mat flat(36, 60, CV_8UC1, cv::Scalar(140));
    EXPECT_FALSE(locate_pupil(flat).has_value());
}

TEST(Pupil, ATinyPatchIsRefused) {
    EXPECT_FALSE(locate_pupil(cv::Mat(4, 4, CV_8UC1, cv::Scalar(0))).has_value());
}
