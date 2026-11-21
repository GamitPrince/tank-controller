# ztest application for the measurement layer, built by Twister on native_sim.
cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(measurement_scaling)

set(MEASUREMENT_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../src/measurement)

target_sources(app PRIVATE
  src/main.c
  ${MEASUREMENT_DIR}/scaling.c
)

target_include_directories(app PRIVATE ${MEASUREMENT_DIR})
