# ztest application for the one-second scan builder (S-058, P1-12), built by
# Twister on native_sim. It drives the real input modules, so their status
# rules are what the builder is tested against.
cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(record_scan_builder)

set(SRC_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../src)

target_sources(app PRIVATE
  src/main.c
  ${SRC_DIR}/record/scan_builder.c
  ${SRC_DIR}/record/scan_codec.c
  ${SRC_DIR}/record/boot_time.c
  ${SRC_DIR}/safety/level_switch.c
  ${SRC_DIR}/measurement/loop_level.c
  ${SRC_DIR}/measurement/product_temperature.c
  ${SRC_DIR}/measurement/pt100.c
  ${SRC_DIR}/hardware/ad4111.c
  ${SRC_DIR}/hardware/max31865.c
)

target_include_directories(app PRIVATE
  ${SRC_DIR}/record
  ${SRC_DIR}/safety
  ${SRC_DIR}/measurement
  ${SRC_DIR}/hardware
)

# pt100.c uses sqrtf(); native_sim's toolchain does not always pull libm in.
target_link_libraries(app PRIVATE m)
