// Turning labelled frames into flagged spans: thresholds, gaps, merging, confidence.
#include <gtest/gtest.h>

#include <utility>
#include <vector>

#include "zeg_gaze/gaze.hpp"

using namespace zeg::gaze;

namespace {

constexpr double kFps = 10.0;

// A timeline of (label, seconds) played at 10 fps. `raw` defaults to the label itself.
std::vector<FrameResult> timeline(const std::vector<std::pair<Label, double>>& parts) {
    std::vector<FrameResult> out;
    int64_t i = 0;
    for (const auto& [label, secs] : parts) {
        const int n = static_cast<int>(secs * kFps + 0.5);
        for (int k = 0; k < n; ++k, ++i) {
            FrameResult r;
            r.index = i;
            r.t_s = i / kFps;
            r.label = r.raw = label;
            r.confidence = 1.0;
            out.push_back(r);
        }
    }
    return out;
}

std::vector<Flag> run(const std::vector<FrameResult>& frames, const Config& c = Config()) {
    Segmenter s(c);
    std::vector<Flag> flags;
    for (const auto& f : frames) {
        s.push(f);
        for (auto& x : s.take_closed()) flags.push_back(x);
    }
    for (auto& x : s.finish()) flags.push_back(x);
    return merge_flags(flags, c.merge_gap_s);
}

}  // namespace

TEST(Segments, ShortLooksAwayAreNotFlagged) {
    auto flags = run(timeline({{Label::OnScreen, 10}, {Label::AwayLeft, 4.5}, {Label::OnScreen, 10}}));
    EXPECT_TRUE(flags.empty());
}

TEST(Segments, LookingAwayPastTheThresholdIsFlaggedWithItsSpan) {
    auto flags = run(timeline({{Label::OnScreen, 10}, {Label::AwayLeft, 6}, {Label::OnScreen, 10}}));
    ASSERT_EQ(flags.size(), 1u);
    EXPECT_EQ(flags[0].reason, Reason::LookingAway);
    EXPECT_EQ(flags[0].direction, "left");
    EXPECT_NEAR(flags[0].start_s, 10.0, 0.11);
    EXPECT_NEAR(flags[0].end_s, 16.0, 0.11);
    EXPECT_NEAR(flags[0].confidence, 1.0, 1e-9);
    // The still to review comes from the middle of the span.
    EXPECT_NEAR(flags[0].sample_t_s, 13.0, 0.15);
    EXPECT_EQ(flags[0].sample_frame, static_cast<int64_t>(flags[0].sample_t_s * kFps + 0.5));
}

TEST(Segments, TheThresholdIsConfigurable) {
    Config c;
    c.away_threshold_s = 3.0;
    auto flags = run(timeline({{Label::OnScreen, 5}, {Label::AwayRight, 4}, {Label::OnScreen, 5}}), c);
    ASSERT_EQ(flags.size(), 1u);
    EXPECT_EQ(flags[0].direction, "right");
}

TEST(Segments, ABriefGlanceBackDoesNotSplitARun) {
    // 3 s away, 0.3 s back on screen, 3 s away: one continuous 6.3 s span.
    auto flags = run(timeline({{Label::OnScreen, 5}, {Label::AwayDown, 3}, {Label::OnScreen, 0.3},
                               {Label::AwayDown, 3}, {Label::OnScreen, 5}}));
    ASSERT_EQ(flags.size(), 1u);
    EXPECT_NEAR(flags[0].end_s - flags[0].start_s, 6.3, 0.15);
    EXPECT_EQ(flags[0].direction, "down");
    // The frames that were back on screen count against the span's confidence.
    EXPECT_LT(flags[0].confidence, 1.0);
    EXPECT_GT(flags[0].confidence, 0.9);
}

TEST(Segments, ALongerLookBackEndsTheRun) {
    // Each piece is under the threshold, and 2 s on screen between them is a real return.
    auto flags = run(timeline({{Label::AwayLeft, 3}, {Label::OnScreen, 2}, {Label::AwayLeft, 3}}));
    EXPECT_TRUE(flags.empty());
}

TEST(Segments, NearbyFlagsOfOneReasonAreMerged) {
    const auto frames = timeline({{Label::AwayLeft, 6}, {Label::OnScreen, 0.8}, {Label::AwayRight, 6}});
    auto merged = run(frames);
    ASSERT_EQ(merged.size(), 1u);
    EXPECT_EQ(merged[0].direction, "mixed");
    EXPECT_NEAR(merged[0].end_s - merged[0].start_s, 12.8, 0.15);

    Config tight;
    tight.merge_gap_s = 0.5;
    EXPECT_EQ(run(frames, tight).size(), 2u);
}

TEST(Segments, MergeKeepsReasonsApart) {
    Flag a, b;
    a.start_s = 0; a.end_s = 6; a.reason = Reason::NoFace;
    b.start_s = 6.2; b.end_s = 12; b.reason = Reason::LookingAway;
    EXPECT_EQ(merge_flags({a, b}, 1.0).size(), 2u);
    b.reason = Reason::NoFace;
    auto one = merge_flags({b, a}, 1.0);  // order in does not matter
    ASSERT_EQ(one.size(), 1u);
    EXPECT_DOUBLE_EQ(one[0].start_s, 0);
    EXPECT_DOUBLE_EQ(one[0].end_s, 12);
}

TEST(Segments, NoFaceAndMultipleFacesHaveTheirOwnThresholds) {
    auto flags = run(timeline({{Label::OnScreen, 5}, {Label::NoFace, 6}, {Label::OnScreen, 5},
                               {Label::MultipleFaces, 2.5}, {Label::OnScreen, 5},
                               {Label::MultipleFaces, 1.5}, {Label::OnScreen, 5}}));
    ASSERT_EQ(flags.size(), 2u);
    EXPECT_EQ(flags[0].reason, Reason::NoFace);
    EXPECT_TRUE(flags[0].direction.empty());
    EXPECT_EQ(flags[1].reason, Reason::MultipleFaces);
    EXPECT_NEAR(flags[1].start_s, 16.0, 0.11);
}

TEST(Segments, ASpanOpenAtTheEndOfTheCallIsClosedByFinish) {
    auto flags = run(timeline({{Label::OnScreen, 5}, {Label::AwayRight, 7}}));
    ASSERT_EQ(flags.size(), 1u);
    EXPECT_NEAR(flags[0].end_s, 12.0, 0.11);
}

TEST(Segments, LiveCallersGetAFlagSoonAfterItCloses) {
    Segmenter s;
    const auto frames = timeline({{Label::OnScreen, 2}, {Label::NoFace, 6}, {Label::OnScreen, 3}, {Label::OnScreen, 30}});
    size_t seen_at = 0;
    for (size_t i = 0; i < frames.size(); ++i) {
        s.push(frames[i]);
        if (!s.take_closed().empty()) {
            seen_at = i;
            break;
        }
    }
    ASSERT_GT(seen_at, 0u);
    // Closed at 8 s, released once the merge window (1 s) has passed.
    EXPECT_LT(frames[seen_at].t_s, 10.0);
}

TEST(Segments, ConfidenceIsTheShareOfRawFramesThatAgree) {
    auto frames = timeline({{Label::OnScreen, 2}, {Label::AwayLeft, 10}, {Label::OnScreen, 2}});
    // Smoothing said "away" for all ten seconds; the raw frames agreed only half the time.
    for (auto& f : frames) {
        if (f.label == Label::AwayLeft && f.index % 2) f.raw = Label::OnScreen;
    }
    auto flags = run(frames);
    ASSERT_EQ(flags.size(), 1u);
    EXPECT_NEAR(flags[0].confidence, 0.5, 0.02);
}

TEST(Json, ShapeIsTheDocumentedOne) {
    Flag f;
    f.start_s = 12.5; f.end_s = 19.25; f.reason = Reason::LookingAway; f.direction = "left";
    f.confidence = 0.87; f.sample_frame = 238; f.sample_t_s = 15.9;
    const std::string json = flags_to_json({f});
    EXPECT_NE(json.find("\"start_s\": 12.50"), std::string::npos);
    EXPECT_NE(json.find("\"end_s\": 19.25"), std::string::npos);
    EXPECT_NE(json.find("\"reason\": \"looking_away\""), std::string::npos);
    EXPECT_NE(json.find("\"confidence\": 0.87"), std::string::npos);
    EXPECT_NE(json.find("\"sample_frame\": 238"), std::string::npos);
    EXPECT_EQ(flags_to_json({}), "[]");
}
