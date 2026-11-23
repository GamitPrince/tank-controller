# ztest application for the alarm and trip status reads (S-031, P1-09),
# built by Twister on native_sim.
cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(safety_alarm_input)

set(SAFETY_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../src/safety)
set(FIRMWARE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../..)
set(SIGNAL_LIST ${FIRMWARE_DIR}/../interfaces/signals-v1.yaml)
set(GENERATED_DIR ${CMAKE_CURRENT_BINARY_DIR}/generated)
set(GENERATED_HEADER ${GENERATED_DIR}/tank_safety_signals.h)

# The signal list in interfaces/ is the contract (ADR-0004 decision 9), so the
# ids, channels, contact senses and debounce figures are generated from it at
# build time rather than written into C. A change to the YAML rebuilds this.
add_custom_command(
  OUTPUT ${GENERATED_HEADER}
  COMMAND ${PYTHON_EXECUTABLE} ${FIRMWARE_DIR}/scripts/gen_safety_signals.py
          --signals ${SIGNAL_LIST}
          --output ${GENERATED_HEADER}
          --story P1-09
  DEPENDS ${FIRMWARE_DIR}/scripts/gen_safety_signals.py ${SIGNAL_LIST}
  COMMENT "Generating the P1-09 alarm input table from signals-v1.yaml"
  VERBATIM
)

add_custom_target(tank_safety_signals DEPENDS ${GENERATED_HEADER})

target_sources(app PRIVATE
  src/main.c
  ${SAFETY_DIR}/level_switch.c
  ${SAFETY_DIR}/alarm_input_config.c
)

target_include_directories(app PRIVATE ${SAFETY_DIR} ${GENERATED_DIR})
add_dependencies(app tank_safety_signals)
