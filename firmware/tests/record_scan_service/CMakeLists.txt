# ztest application for the one-second scan service (S-059), built by Twister
# on native_sim's flash simulator. It reuses the outage buffer tests' 10 MB
# simulated flash and the real input modules.
cmake_minimum_required(VERSION 3.20.0)

set(FLASH_LOG_TEST_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../record_flash_log)
set(DTC_OVERLAY_FILE ${FLASH_LOG_TEST_DIR}/app.overlay)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(record_scan_service)

set(SRC_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../src)

target_sources(app PRIVATE
  src/main.c
  ${FLASH_LOG_TEST_DIR}/src/scan_gen.c
  ${SRC_DIR}/record/scan_service.c
  ${SRC_DIR}/record/scan_builder.c
  ${SRC_DIR}/record/scan_codec.c
  ${SRC_DIR}/record/flash_log.c
  ${SRC_DIR}/record/boot_time.c
  ${SRC_DIR}/safety/level_switch.c
  ${SRC_DIR}/measurement/loop_level.c
  ${SRC_DIR}/measurement/product_temperature.c
  ${SRC_DIR}/measurement/pt100.c
  ${SRC_DIR}/hardware/ad4111.c
  ${SRC_DIR}/hardware/max31865.c
)

target_include_directories(app PRIVATE
  ${FLASH_LOG_TEST_DIR}/src
  ${SRC_DIR}/record
  ${SRC_DIR}/safety
  ${SRC_DIR}/measurement
  ${SRC_DIR}/hardware
)

# pt100.c uses sqrtf(); native_sim's toolchain does not always pull libm in.
target_link_libraries(app PRIVATE m)
