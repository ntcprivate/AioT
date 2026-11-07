cmake_minimum_required(VERSION 3.16)

# Default to the original ESP32, never ESP32-S3/C3.
set(IDF_TARGET "esp32" CACHE STRING "Target chip")
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(esp32_ad8232_adc_test)

if(NOT IDF_TARGET STREQUAL "esp32")
    message(FATAL_ERROR "This project requires ESP32 DevKit V1 / ESP32-WROOM-32 (target esp32)")
endif()
