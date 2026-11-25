# ztest application for the outage buffer: flash log and forwarder
# (S-039, P1-14), built by Twister on native_sim's flash simulator.
cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(record_flash_log)

set(RECORD_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../src/record)
set(COMMS_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../src/communications)

target_sources(app PRIVATE
  src/main.c
  src/scan_gen.c
  src/test_forwarder.c
  ${RECORD_DIR}/scan_codec.c
  ${RECORD_DIR}/flash_log.c
  ${COMMS_DIR}/log_forwarder.c
)

target_include_directories(app PRIVATE ${RECORD_DIR} ${COMMS_DIR})
