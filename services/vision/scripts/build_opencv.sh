#!/usr/bin/env bash
# Build a minimal OpenCV (core, imgproc, objdetect, imgcodecs, videoio) from source.
#
# Only for a machine with no package manager copy of OpenCV. On macOS with Homebrew,
# `brew install opencv` is simpler; on Linux (and the GB10 box, Ubuntu on arm64),
# `sudo apt install libopencv-dev` is. See services/vision/README.md.
#
#   services/vision/scripts/build_opencv.sh [prefix]     # default ~/.local/opencv
#
# Needs cmake and a C++17 compiler. `pip install cmake ninja` is enough for cmake.
set -euo pipefail

VERSION="${OPENCV_VERSION:-4.11.0}"
PREFIX="${1:-$HOME/.local/opencv}"
WORK="${TMPDIR:-/tmp}/zeg-opencv-build"
CMAKE="${CMAKE:-cmake}"

mkdir -p "$WORK"
cd "$WORK"
if [ ! -d "opencv-$VERSION" ]; then
  curl -fsSL "https://github.com/opencv/opencv/archive/refs/tags/$VERSION.tar.gz" -o opencv.tgz
  tar xzf opencv.tgz
fi

GEN=()
if command -v ninja >/dev/null 2>&1; then GEN=(-G Ninja); fi

"$CMAKE" -S "opencv-$VERSION" -B build "${GEN[@]}" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$PREFIX" \
  -DBUILD_LIST=core,imgproc,objdetect,imgcodecs,videoio \
  -DBUILD_SHARED_LIBS=ON \
  -DBUILD_TESTS=OFF -DBUILD_PERF_TESTS=OFF -DBUILD_EXAMPLES=OFF -DBUILD_DOCS=OFF \
  -DBUILD_opencv_apps=OFF -DBUILD_opencv_python3=OFF -DBUILD_JAVA=OFF \
  -DWITH_FFMPEG=ON -DWITH_GSTREAMER=OFF -DWITH_OPENCL=OFF -DWITH_IPP=OFF \
  -DWITH_ADE=OFF -DWITH_PROTOBUF=OFF -DWITH_EIGEN=OFF -DWITH_QT=OFF -DWITH_GTK=OFF \
  -DOPENCV_GENERATE_PKGCONFIG=OFF -DCMAKE_POLICY_VERSION_MINIMUM=3.5
"$CMAKE" --build build --parallel
"$CMAKE" --install build
echo "OpenCV $VERSION installed to $PREFIX"
echo "configure zeg-gaze with: -DOpenCV_DIR=$PREFIX/lib/cmake/opencv4"
