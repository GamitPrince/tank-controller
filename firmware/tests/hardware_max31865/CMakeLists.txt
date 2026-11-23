# ztest application for the MAX31865 register decode (S-032, P1-06),
# built by Twister on native_sim.
cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(hardware_max31865)

set(HARDWARE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../src/hardware)

target_sources(app PRIVATE
  src/main.c
  ${HARDWARE_DIR}/max31865.c
)

target_include_directories(app PRIVATE ${HARDWARE_DIR})
