// Per-frame classification from what the detector saw.
#include <gtest/gtest.h>

#include "zeg_gaze/gaze.hpp"

using namespace zeg::gaze;

namespace {

FrameObservation frontal(bool offsets = true) {
    FrameObservation o;
    FaceResult f;
    f.box = cv::Rect(200, 120, 200, 200);
    o.faces.push_back(f);
    if (offsets) {
        o.has_offsets = true;
        o.eyes.resize(2);
    }
    return o;
}

}  // namespace

TEST(Classify, NoFaceAndMoreThanOne) {
    const Config c;
    FrameObservation none;
    EXPECT_EQ(classify(none, 0, 0, true, c).label, Label::NoFace);
    FrameObservation two = frontal();
    two.faces.push_back(two.faces.front());
    EXPECT_EQ(classify(two, 0, 0, true, c).label, Label::MultipleFaces);
}

TEST(Classify, AProfileIsAHeadTurnedAway) {
    const Config c;
    FrameObservation o;
    FaceResult f;
    f.profile = true;
    f.facing_image_right = true;  // nose to the image right: the candidate's own left
    o.faces.push_back(f);
    EXPECT_EQ(classify(o, 0, 0, true, c).label, Label::AwayLeft);
    o.faces[0].facing_image_right = false;
    EXPECT_EQ(classify(o, 0, 0, true, c).label, Label::AwayRight);
}

TEST(Classify, OffsetsPastTheThreshold) {
    const Config c;
    const auto o = frontal();
    EXPECT_EQ(classify(o, 0.0, 0.0, true, c).label, Label::OnScreen);
    EXPECT_EQ(classify(o, c.horizontal_threshold * 0.9, 0.0, true, c).label, Label::OnScreen);
    EXPECT_EQ(classify(o, c.horizontal_threshold * 1.2, 0.0, true, c).label, Label::AwayLeft);
    EXPECT_EQ(classify(o, -c.horizontal_threshold * 1.2, 0.0, true, c).label, Label::AwayRight);
    EXPECT_EQ(classify(o, 0.0, c.down_threshold * 1.3, true, c).label, Label::AwayDown);
    // Looking up is not flagged: it is what people do when they think.
    EXPECT_EQ(classify(o, 0.0, -c.down_threshold * 2, true, c).label, Label::OnScreen);
}

TEST(Classify, ConfidenceGrowsWithDistanceFromTheThreshold) {
    const Config c;
    const auto o = frontal();
    const double near = classify(o, c.horizontal_threshold * 1.05, 0, true, c).confidence;
    const double far = classify(o, c.horizontal_threshold * 1.9, 0, true, c).confidence;
    EXPECT_LT(near, far);
    EXPECT_LE(far, 1.0);
    EXPECT_GT(classify(o, 0, 0, true, c).confidence, classify(o, c.horizontal_threshold * 0.9, 0, true, c).confidence);
}

TEST(Classify, MissingEyesMeanDownOnlyForSomeoneWhoseEyesAreUsuallyFound) {
    const Config c;
    const auto o = frontal(false);
    EXPECT_EQ(classify(o, 0, 0, true, c).label, Label::AwayDown);
    // Glasses glare: eyes are rarely found, so their absence says nothing.
    EXPECT_EQ(classify(o, 0, 0, false, c).label, Label::OnScreen);
}

TEST(Labels, NamesRoundTrip) {
    for (int i = 0; i <= static_cast<int>(Label::MultipleFaces); ++i) {
        const Label l = static_cast<Label>(i);
        EXPECT_EQ(label_from_name(label_name(l)), l);
    }
    EXPECT_FALSE(label_from_name("cheating").has_value());
    EXPECT_EQ(reason_for(Label::OnScreen), std::nullopt);
    EXPECT_EQ(reason_for(Label::AwayDown), Reason::LookingAway);
}
