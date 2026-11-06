cmake_minimum_required(VERSION 3.22)

set(IDF_TARGET esp32s3 CACHE STRING "ESPaperPlay target")
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
set(PROJECT_VER "0.3.0-dev")
set(COMPONENTS main)
project(ESPaperPlay_v2)

if(NOT IDF_TARGET STREQUAL "esp32s3")
    message(FATAL_ERROR "The current board profile requires ESP32-S3")
endif()
