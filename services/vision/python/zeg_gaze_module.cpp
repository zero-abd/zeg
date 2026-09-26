// Python binding: `import zeg_gaze`. The gateway feeds live frames through Session and
// runs process_video on a recording after the call. Frames arrive as any object with
// the buffer protocol (bytes, a PyAV plane, a numpy array), so numpy is not required.
#include <pybind11/functional.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <opencv2/imgcodecs.hpp>

#include "zeg_gaze/gaze.hpp"

namespace py = pybind11;
using namespace zeg::gaze;

namespace {

py::dict flag_dict(const Flag& f) {
    py::dict d;
    d["start_s"] = f.start_s;
    d["end_s"] = f.end_s;
    d["reason"] = reason_name(f.reason);
    if (!f.direction.empty()) d["direction"] = f.direction;
    d["confidence"] = f.confidence;
    d["sample_frame"] = f.sample_frame;
    d["sample_t_s"] = f.sample_t_s;
    if (!f.sample_image.empty()) d["sample_image"] = f.sample_image;
    return d;
}

py::list flag_list(const std::vector<Flag>& flags) {
    py::list out;
    for (const Flag& f : flags) out.append(flag_dict(f));
    return out;
}

py::dict frame_dict(const FrameResult& r) {
    py::dict d;
    d["index"] = r.index;
    d["t_s"] = r.t_s;
    d["raw"] = label_name(r.raw);
    d["label"] = label_name(r.label);
    d["confidence"] = r.confidence;
    d["faces"] = r.faces;
    d["eyes"] = r.eyes;
    d["h_offset"] = r.h_offset;
    d["v_offset"] = r.v_offset;
    return d;
}

Config make_config(double threshold_s, double no_face_threshold_s, double multi_face_threshold_s,
                   int smooth_window) {
    Config c;
    c.away_threshold_s = threshold_s;
    c.no_face_threshold_s = no_face_threshold_s < 0 ? threshold_s : no_face_threshold_s;
    c.multi_face_threshold_s = multi_face_threshold_s;
    c.smooth_window = smooth_window;
    return c;
}

}  // namespace

PYBIND11_MODULE(zeg_gaze, m) {
    m.doc() = "Haar-cascade face and gaze review flags for zeg calls (see docs/12-video-review.md)";

    py::class_<Session>(m, "Session")
        .def(py::init([](double threshold_s, double no_face_threshold_s, double multi_face_threshold_s,
                         int smooth_window, const std::string& cascades) {
                 return std::make_unique<Session>(
                     make_config(threshold_s, no_face_threshold_s, multi_face_threshold_s, smooth_window),
                     cascades);
             }),
             py::arg("threshold_s") = 5.0, py::arg("no_face_threshold_s") = -1.0,
             py::arg("multi_face_threshold_s") = 2.0, py::arg("smooth_window") = 9,
             py::arg("cascades") = "")
        .def(
            "push_bgr",
            [](Session& s, py::buffer frame, int width, int height, size_t stride, double t_s) {
                py::buffer_info info = frame.request();
                const size_t row = stride ? stride : static_cast<size_t>(width) * 3;
                const size_t need = row * (height - 1) + static_cast<size_t>(width) * 3;
                if (static_cast<size_t>(info.size * info.itemsize) < need) {
                    throw py::value_error("frame buffer is smaller than width x height x 3");
                }
                std::vector<FrameResult> done;
                {
                    py::gil_scoped_release release;
                    done = s.push_bgr(static_cast<const uint8_t*>(info.ptr), width, height, row, t_s);
                }
                py::list out;
                for (const auto& r : done) out.append(frame_dict(r));
                return out;
            },
            py::arg("frame"), py::arg("width"), py::arg("height"), py::arg("stride") = 0, py::arg("t_s"),
            "Push one BGR frame. Returns the frames whose label became final.")
        .def("take_closed", [](Session& s) { return flag_list(s.take_closed()); },
             "Flags that closed since the last call.")
        .def("finish", [](Session& s) {
                 std::vector<Flag> flags;
                 {
                     py::gil_scoped_release release;
                     flags = s.finish();
                 }
                 return flag_list(flags);
             },
             "End of call: close open spans and return the remaining flags.")
        .def_property_readonly("frames", &Session::frames);

    m.def(
        "process_video",
        [](const std::string& path, double threshold_s, double no_face_threshold_s,
           double multi_face_threshold_s, int smooth_window, const std::string& cascades,
           const std::string& samples) {
            VideoSummary s;
            {
                py::gil_scoped_release release;
                s = process_video(path,
                                  make_config(threshold_s, no_face_threshold_s, multi_face_threshold_s,
                                              smooth_window),
                                  cascades, samples);
            }
            py::dict d;
            d["flags"] = flag_list(s.flags);
            d["frames"] = s.frames;
            d["duration_s"] = s.duration_s;
            d["processing_fps"] = s.processing_fps;
            d["analysis_fps"] = s.analysis_fps;
            d["width"] = s.width;
            d["height"] = s.height;
            return d;
        },
        py::arg("path"), py::arg("threshold_s") = 5.0, py::arg("no_face_threshold_s") = -1.0,
        py::arg("multi_face_threshold_s") = 2.0, py::arg("smooth_window") = 9, py::arg("cascades") = "",
        py::arg("samples") = "",
        "Run a recorded call video through the detector. Returns flags and timing.");

    m.def("default_cascade_dir", &default_cascade_dir);

    m.def(
        "read_image",
        [](const std::string& path) {
            const cv::Mat img = cv::imread(path, cv::IMREAD_COLOR);
            if (img.empty()) throw py::value_error("cannot read image " + path);
            const cv::Mat packed = img.isContinuous() ? img : img.clone();
            return py::make_tuple(
                py::bytes(reinterpret_cast<const char*>(packed.data), packed.total() * packed.elemSize()),
                packed.cols, packed.rows);
        },
        py::arg("path"), "An image file as (BGR bytes, width, height), for tests and tools.");
}
