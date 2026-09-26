// zeg-gaze: flag moments of a call video for a human to review.
//
//   zeg-gaze <video> --out flags.json [--threshold 5]
//   zeg-gaze --stdin --width 640 --height 480 [--out flags.json]
//
// The second form reads live frames from stdin, each an 8-byte little-endian double
// timestamp in seconds followed by width*height*3 bytes of BGR, and prints each flag as
// one JSON line on stdout as soon as it closes. It is the subprocess path for a gateway
// that cannot load the Python module.
#include <chrono>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

#include "zeg_gaze/gaze.hpp"

using namespace zeg::gaze;

namespace {

void usage() {
    std::fprintf(stderr,
        "usage: zeg-gaze <video> [--out flags.json] [options]\n"
        "       zeg-gaze --stdin --width W --height H [--out flags.json] [options]\n"
        "\n"
        "options:\n"
        "  --threshold S             flag looking away for longer than S seconds (default 5)\n"
        "  --no-face-threshold S     flag no face for longer than S seconds (default: --threshold)\n"
        "  --multi-face-threshold S  flag more than one face for longer than S seconds (default 2)\n"
        "  --smooth N                smoothing window in frames, odd (default 9)\n"
        "  --cascades DIR            directory with the haarcascade_*.xml files\n"
        "  --samples DIR             save a JPEG of the middle frame of each flag\n"
        "  --per-frame FILE          write every frame's label as CSV\n"
        "  --quiet                   no summary on stderr\n");
}

bool read_exact(std::istream& in, char* buf, size_t n) {
    in.read(buf, static_cast<std::streamsize>(n));
    return static_cast<size_t>(in.gcount()) == n;
}

}  // namespace

int main(int argc, char** argv) {
    std::string video, out, cascades, samples, per_frame_path;
    bool from_stdin = false, quiet = false;
    int width = 0, height = 0;
    Config config;
    bool no_face_set = false;
    try {
        for (int i = 1; i < argc; ++i) {
            const std::string a = argv[i];
            auto next = [&]() -> std::string {
                if (i + 1 >= argc) throw std::runtime_error("missing value for " + a);
                return argv[++i];
            };
            if (a == "--out" || a == "-o") out = next();
            else if (a == "--threshold") config.away_threshold_s = std::stod(next());
            else if (a == "--no-face-threshold") { config.no_face_threshold_s = std::stod(next()); no_face_set = true; }
            else if (a == "--multi-face-threshold") config.multi_face_threshold_s = std::stod(next());
            else if (a == "--smooth") config.smooth_window = std::stoi(next());
            else if (a == "--cascades") cascades = next();
            else if (a == "--samples") samples = next();
            else if (a == "--per-frame") per_frame_path = next();
            else if (a == "--stdin") from_stdin = true;
            else if (a == "--width") width = std::stoi(next());
            else if (a == "--height") height = std::stoi(next());
            else if (a == "--quiet" || a == "-q") quiet = true;
            else if (a == "--help" || a == "-h") { usage(); return 0; }
            else if (!a.empty() && a[0] == '-') throw std::runtime_error("unknown option " + a);
            else video = a;
        }
        if (!no_face_set) config.no_face_threshold_s = config.away_threshold_s;
        if (from_stdin == !video.empty()) {
            usage();
            return 2;
        }

        std::ofstream per_frame;
        if (!per_frame_path.empty()) {
            per_frame.open(per_frame_path);
            per_frame << "index,t_s,raw,label,confidence,faces,eyes,h_offset,v_offset\n";
        }
        auto write_frame = [&](const FrameResult& r) {
            if (!per_frame.is_open()) return;
            char line[256];
            std::snprintf(line, sizeof line, "%lld,%.3f,%s,%s,%.2f,%d,%d,%.4f,%.4f\n",
                          static_cast<long long>(r.index), r.t_s, label_name(r.raw), label_name(r.label),
                          r.confidence, r.faces, r.eyes, r.h_offset, r.v_offset);
            per_frame << line;
        };

        std::vector<Flag> flags;
        if (from_stdin) {
            if (width <= 0 || height <= 0) throw std::runtime_error("--stdin needs --width and --height");
            Session session(config, cascades);
            std::vector<char> buf(static_cast<size_t>(width) * height * 3);
            double t = 0.0;
            const auto started = std::chrono::steady_clock::now();
            while (read_exact(std::cin, reinterpret_cast<char*>(&t), sizeof t) &&
                   read_exact(std::cin, buf.data(), buf.size())) {
                for (const auto& r : session.push_bgr(reinterpret_cast<uint8_t*>(buf.data()), width, height, 0, t)) {
                    write_frame(r);
                }
                for (const Flag& f : session.take_closed()) {
                    const std::string one = flags_to_json({f}, 0);
                    std::cout << one.substr(1, one.size() - 2) << "\n" << std::flush;
                    flags.push_back(f);
                }
            }
            for (const Flag& f : session.finish()) {
                const std::string one = flags_to_json({f}, 0);
                std::cout << one.substr(1, one.size() - 2) << "\n" << std::flush;
                flags.push_back(f);
            }
            const double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count();
            if (!quiet) {
                std::fprintf(stderr, "zeg-gaze: %lld frames from stdin, %.1f fps, %zu flags\n",
                             static_cast<long long>(session.frames()), wall > 0 ? session.frames() / wall : 0.0,
                             flags.size());
            }
        } else {
            VideoSummary s = process_video(video, config, cascades, samples, write_frame);
            flags = s.flags;
            if (!quiet) {
                std::fprintf(stderr,
                             "zeg-gaze: %s %dx%d, %lld frames, %.1f s; %.1f fps end to end, "
                             "%.1f fps analysis; %zu flags\n",
                             video.c_str(), s.width, s.height, static_cast<long long>(s.frames), s.duration_s,
                             s.processing_fps, s.analysis_fps, flags.size());
            }
        }

        const std::string json = flags_to_json(flags);
        if (out.empty() || out == "-") {
            if (!from_stdin) std::cout << json << "\n";
        } else {
            std::ofstream f(out);
            if (!f) throw std::runtime_error("cannot write " + out);
            f << json << "\n";
        }
    } catch (const std::exception& e) {
        std::fprintf(stderr, "zeg-gaze: %s\n", e.what());
        return 1;
    }
    return 0;
}
