# ztest application for the CBOR record encoder (S-044, P1-12), built by
# Twister on native_sim.
cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(record_cbor)

set(SRC_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../src)
# The shared link library (S-056, ADR-0003 amendment 1), also built for the ESP32.
set(LINK_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../../shared/link-protocol)

target_sources(app PRIVATE
  src/main.c
  ${SRC_DIR}/record/record_cbor.c
)

target_include_directories(app PRIVATE
  ${SRC_DIR}/record
  ${SRC_DIR}/measurement
  ${SRC_DIR}/communications
  ${LINK_DIR}
)
