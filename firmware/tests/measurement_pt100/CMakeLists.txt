# ztest application for the PT100 linearisation (S-032, P1-06),
# built by Twister on native_sim.
cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(measurement_pt100)

set(MEASUREMENT_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../src/measurement)

target_sources(app PRIVATE
  src/main.c
  ${MEASUREMENT_DIR}/pt100.c
)

target_include_directories(app PRIVATE ${MEASUREMENT_DIR})

# pt100.c calls sqrtf(); native_sim's toolchain does not always pull libm in
# on its own.
target_link_libraries(app PRIVATE m)
