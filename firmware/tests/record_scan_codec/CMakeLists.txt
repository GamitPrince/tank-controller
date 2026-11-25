# ztest application for the flash log's scan encoding (S-039, P1-14),
# built by Twister on native_sim.
cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(record_scan_codec)

set(RECORD_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../src/record)

target_sources(app PRIVATE
  src/main.c
  ${RECORD_DIR}/scan_codec.c
)

target_include_directories(app PRIVATE ${RECORD_DIR})
