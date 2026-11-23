# ztest application for the AD4111 data decode (S-034, P1-04),
# built by Twister on native_sim.
cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(hardware_ad4111)

set(HARDWARE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../src/hardware)

target_sources(app PRIVATE
  src/main.c
  ${HARDWARE_DIR}/ad4111.c
)

target_include_directories(app PRIVATE ${HARDWARE_DIR})
