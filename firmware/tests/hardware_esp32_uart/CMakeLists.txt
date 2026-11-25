# ztest application for the FRDM-to-ESP32 UART driver glue (S-048), built by
# Twister on native_sim with Zephyr's emulated UART. The end-to-end test
# reuses the outage buffer tests' scan generator and 10 MB simulated flash.
cmake_minimum_required(VERSION 3.20.0)

set(FLASH_LOG_TEST_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../record_flash_log)
set(DTC_OVERLAY_FILE "${FLASH_LOG_TEST_DIR}/app.overlay;${CMAKE_CURRENT_SOURCE_DIR}/uart.overlay")

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(hardware_esp32_uart)

set(SRC_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../src)

target_sources(app PRIVATE
  src/main.c
  src/end_to_end.c
  ${FLASH_LOG_TEST_DIR}/src/scan_gen.c
  ${SRC_DIR}/hardware/esp32_uart.c
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
  ${FLASH_LOG_TEST_DIR}/src
  ${SRC_DIR}/hardware
  ${SRC_DIR}/record
  ${SRC_DIR}/measurement
  ${SRC_DIR}/communications
)
