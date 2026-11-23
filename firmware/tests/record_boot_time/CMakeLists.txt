# ztest application for boot-relative time bookkeeping (S-038, P1-15),
# built by Twister on native_sim.
cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(record_boot_time)

set(RECORD_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../src/record)

target_sources(app PRIVATE
  src/main.c
  ${RECORD_DIR}/boot_time.c
)

target_include_directories(app PRIVATE ${RECORD_DIR})
