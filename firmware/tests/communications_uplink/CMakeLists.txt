# ztest application for forwarding the flash log over the UART link
# (S-045), built by Twister on native_sim. It reuses the outage buffer
# tests' scan generator and their 10 MB simulated flash.
cmake_minimum_required(VERSION 3.20.0)

set(FLASH_LOG_TEST_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../record_flash_log)
set(DTC_OVERLAY_FILE ${FLASH_LOG_TEST_DIR}/app.overlay)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(communications_uplink)

set(SRC_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../src)

target_sources(app PRIVATE
  src/main.c
  src/sim_link.c
  ${FLASH_LOG_TEST_DIR}/src/scan_gen.c
  ${SRC_DIR}/record/scan_codec.c
  ${SRC_DIR}/record/flash_log.c
  ${SRC_DIR}/record/record_cbor.c
  ${SRC_DIR}/communications/link_frame.c
  ${SRC_DIR}/communications/link_receiver.c
  ${SRC_DIR}/communications/link_sender.c
  ${SRC_DIR}/communications/log_forwarder.c
  ${SRC_DIR}/communications/uplink.c
)

target_include_directories(app PRIVATE
  src
  ${FLASH_LOG_TEST_DIR}/src
  ${SRC_DIR}/record
  ${SRC_DIR}/measurement
  ${SRC_DIR}/communications
)
