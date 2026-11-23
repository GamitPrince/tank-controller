# ztest application for the SNTP retry policy and health reporting
# (S-038, P1-15), built by Twister on native_sim.
cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(communications_clock_sync)

set(RECORD_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../src/record)
set(COMMUNICATIONS_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../src/communications)
set(MEASUREMENT_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../src/measurement)
set(FIRMWARE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../..)
set(SIGNAL_LIST ${FIRMWARE_DIR}/../interfaces/signals-v1.yaml)
set(GENERATED_DIR ${CMAKE_CURRENT_BINARY_DIR}/generated)
set(GENERATED_HEADER ${GENERATED_DIR}/tank_health_signals.h)

# The signal list in interfaces/ is the contract (ADR-0004 decision 9), so the
# health signal ids are generated from it at build time rather than written
# into C. A change to the YAML rebuilds this.
add_custom_command(
  OUTPUT ${GENERATED_HEADER}
  COMMAND ${PYTHON_EXECUTABLE} ${FIRMWARE_DIR}/scripts/gen_health_signals.py
          --signals ${SIGNAL_LIST}
          --output ${GENERATED_HEADER}
          --story P1-15
  DEPENDS ${FIRMWARE_DIR}/scripts/gen_health_signals.py ${SIGNAL_LIST}
  COMMENT "Generating the P1-15 health signal table from signals-v1.yaml"
  VERBATIM
)

add_custom_target(tank_health_signals DEPENDS ${GENERATED_HEADER})

# sntp_client.c (the real network call) is deliberately not built here: see
# firmware/src/communications/sntp_client.h. This suite injects a fake
# sync_fn instead.
target_sources(app PRIVATE
  src/main.c
  ${RECORD_DIR}/boot_time.c
  ${COMMUNICATIONS_DIR}/clock_sync.c
)

target_include_directories(app PRIVATE ${RECORD_DIR} ${COMMUNICATIONS_DIR} ${MEASUREMENT_DIR}
				 ${GENERATED_DIR})
add_dependencies(app tank_health_signals)
