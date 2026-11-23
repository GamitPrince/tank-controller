# ztest application for the equipment status reads (S-033, P1-27),
# built by Twister on native_sim.
cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(equipment_status)

set(MEASUREMENT_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../src/measurement)
set(SAFETY_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../src/safety)
set(FIRMWARE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../..)
set(SIGNAL_LIST ${FIRMWARE_DIR}/../interfaces/signals-v1.yaml)
set(GENERATED_DIR ${CMAKE_CURRENT_BINARY_DIR}/generated)
set(GENERATED_HEADER ${GENERATED_DIR}/tank_equipment_status_signals.h)

# The signal list in interfaces/ is the contract (ADR-0004 decision 9), so the
# ids, channels, contact senses and debounce figures are generated from it at
# build time rather than written into C. A change to the YAML rebuilds this.
add_custom_command(
  OUTPUT ${GENERATED_HEADER}
  COMMAND ${PYTHON_EXECUTABLE} ${FIRMWARE_DIR}/scripts/gen_equipment_status_signals.py
          --signals ${SIGNAL_LIST}
          --output ${GENERATED_HEADER}
  DEPENDS ${FIRMWARE_DIR}/scripts/gen_equipment_status_signals.py ${SIGNAL_LIST}
  COMMENT "Generating the P1-27 equipment status table from signals-v1.yaml"
  VERBATIM
)

add_custom_target(tank_equipment_status_signals DEPENDS ${GENERATED_HEADER})

# level_switch.c is the generic debounced-contact engine (P1-05, reused by
# P1-09); it is compiled here as a dependency, not owned by this story.
target_sources(app PRIVATE
  src/main.c
  ${SAFETY_DIR}/level_switch.c
  ${MEASUREMENT_DIR}/equipment_status_config.c
)

target_include_directories(app PRIVATE ${MEASUREMENT_DIR} ${SAFETY_DIR} ${GENERATED_DIR})
add_dependencies(app tank_equipment_status_signals)
