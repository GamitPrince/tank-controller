# ztest application for the firmware application boot (S-060), built by
# Twister on native_sim's flash simulator with every signal-list table. It
# reuses the outage buffer tests' 10 MB simulated flash.
cmake_minimum_required(VERSION 3.20.0)

set(FLASH_LOG_TEST_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../record_flash_log)
set(DTC_OVERLAY_FILE ${FLASH_LOG_TEST_DIR}/app.overlay)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(app_tank_app)

set(FIRMWARE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../..)
set(SRC_DIR ${FIRMWARE_DIR}/src)
include(${FIRMWARE_DIR}/cmake/tank_app_sources.cmake)

target_sources(app PRIVATE
  src/main.c
  ${FLASH_LOG_TEST_DIR}/src/scan_gen.c
)
target_include_directories(app PRIVATE ${FLASH_LOG_TEST_DIR}/src)
tank_add_app_sources(app ${CMAKE_CURRENT_BINARY_DIR}/generated)
