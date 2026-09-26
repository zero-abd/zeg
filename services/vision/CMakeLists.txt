cmake_minimum_required(VERSION 3.16)
project(zeg_gaze VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "" FORCE)
endif()

option(ZEG_GAZE_PYTHON "Build the pybind11 module (import zeg_gaze)" ON)
option(ZEG_GAZE_TESTS "Build the GoogleTest suite" ON)

find_package(OpenCV 4 REQUIRED COMPONENTS core imgproc objdetect imgcodecs videoio)

# Where the Haar cascade XML files live. They ship with OpenCV; the path is compiled in as
# the default and can be overridden at run time with ZEG_GAZE_CASCADES or --cascades.
find_path(ZEG_GAZE_CASCADE_DIR haarcascade_frontalface_default.xml
  HINTS
    "${OpenCV_DIR}/../../../share/opencv4/haarcascades"
    "${OpenCV_DIR}/../../share/opencv4/haarcascades"
    "${OpenCV_INSTALL_PATH}/share/opencv4/haarcascades"
  PATHS
    /usr/share/opencv4/haarcascades
    /usr/share/opencv/haarcascades
    /usr/local/share/opencv4/haarcascades
    /opt/homebrew/share/opencv4/haarcascades
  NO_DEFAULT_PATH)
if(NOT ZEG_GAZE_CASCADE_DIR)
  message(WARNING "haarcascade_frontalface_default.xml not found (on Ubuntu: apt install opencv-data); set ZEG_GAZE_CASCADES at run time")
  set(ZEG_GAZE_CASCADE_DIR "")
endif()
message(STATUS "zeg-gaze cascades: ${ZEG_GAZE_CASCADE_DIR}")

add_library(zeg_gaze_core STATIC
  src/detector.cpp
  src/segments.cpp
  src/session.cpp)
target_include_directories(zeg_gaze_core PUBLIC include ${OpenCV_INCLUDE_DIRS})
target_link_libraries(zeg_gaze_core PUBLIC ${OpenCV_LIBS})
target_compile_definitions(zeg_gaze_core PRIVATE ZEG_GAZE_DEFAULT_CASCADES="${ZEG_GAZE_CASCADE_DIR}")
set_target_properties(zeg_gaze_core PROPERTIES POSITION_INDEPENDENT_CODE ON)
if(CMAKE_CXX_COMPILER_ID MATCHES "Clang|GNU")
  target_compile_options(zeg_gaze_core PRIVATE -Wall -Wextra)
endif()

add_executable(zeg-gaze tools/zeg_gaze_cli.cpp)
target_link_libraries(zeg-gaze PRIVATE zeg_gaze_core)

# Shows what the detector sees in one image, for learning and debugging.
add_executable(zeg-gaze-inspect tools/inspect.cpp)
target_link_libraries(zeg-gaze-inspect PRIVATE zeg_gaze_core)

# Builds the synthetic labelled clips for the eval from a few face stills.
add_executable(zeg-gaze-synth tools/synth.cpp)
target_link_libraries(zeg-gaze-synth PRIVATE zeg_gaze_core)

if(ZEG_GAZE_PYTHON)
  find_package(Python COMPONENTS Interpreter Development.Module)
  if(Python_FOUND AND NOT pybind11_DIR)
    execute_process(COMMAND "${Python_EXECUTABLE}" -m pybind11 --cmakedir
                    OUTPUT_VARIABLE _pybind11_dir OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
    if(_pybind11_dir)
      set(pybind11_DIR "${_pybind11_dir}")
    endif()
  endif()
  find_package(pybind11 CONFIG QUIET)
  if(pybind11_FOUND)
    pybind11_add_module(zeg_gaze python/zeg_gaze_module.cpp)
    target_link_libraries(zeg_gaze PRIVATE zeg_gaze_core)
  else()
    message(WARNING "pybind11 not found: skipping the Python module (pip install pybind11)")
  endif()
endif()

if(ZEG_GAZE_TESTS)
  enable_testing()
  find_package(GTest QUIET)
  if(NOT GTest_FOUND)
    include(FetchContent)
    FetchContent_Declare(googletest
      URL https://github.com/google/googletest/archive/refs/tags/v1.15.2.tar.gz
      DOWNLOAD_EXTRACT_TIMESTAMP TRUE)
    set(INSTALL_GTEST OFF CACHE BOOL "" FORCE)
    set(BUILD_GMOCK OFF CACHE BOOL "" FORCE)
    FetchContent_MakeAvailable(googletest)
  endif()
  add_executable(zeg_gaze_tests
    tests/test_pupil.cpp
    tests/test_classify.cpp
    tests/test_segments.cpp
    tests/test_stills.cpp)
  target_link_libraries(zeg_gaze_tests PRIVATE zeg_gaze_core GTest::gtest_main)
  target_compile_definitions(zeg_gaze_tests PRIVATE
    ZEG_GAZE_FIXTURES="${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures")
  include(GoogleTest)
  gtest_discover_tests(zeg_gaze_tests)
endif()
