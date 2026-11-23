# ztest application for the six product temperature reads (S-032, P1-06),
# built by Twister on native_sim.
cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(product_temperature)

set(HARDWARE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../src/hardware)
set(MEASUREMENT_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../src/measurement)
set(FIRMWARE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../..)
set(SIGNAL_LIST ${FIRMWARE_DIR}/../interfaces/signals-v1.yaml)
set(GENERATED_DIR ${CMAKE_CURRENT_BINARY_DIR}/generated)
set(GENERATED_HEADER ${GENERATED_DIR}/tank_temperature_signals.h)

# The signal list in interfaces/ is the contract (ADR-0004 decision 9), so the
# ids, chip selects, mounting positions and valid ranges are generated from it
# at build time rather than written into C. A change to the YAML rebuilds this.
add_custom_command(
  OUTPUT ${GENERATED_HEADER}
  COMMAND ${PYTHON_EXECUTABLE} ${FIRMWARE_DIR}/scripts/gen_temperature_signals.py
          --signals ${SIGNAL_LIST}
          --output ${GENERATED_HEADER}
  DEPENDS ${FIRMWARE_DIR}/scripts/gen_temperature_signals.py ${SIGNAL_LIST}
  COMMENT "Generating the P1-06 sensor table from signals-v1.yaml"
  VERBATIM
)

add_custom_target(tank_temperature_signals DEPENDS ${GENERATED_HEADER})

target_sources(app PRIVATE
  src/main.c
  ${HARDWARE_DIR}/max31865.c
  ${MEASUREMENT_DIR}/pt100.c
  ${MEASUREMENT_DIR}/product_temperature.c
  ${MEASUREMENT_DIR}/product_temperature_config.c
)

target_include_directories(app PRIVATE ${HARDWARE_DIR} ${MEASUREMENT_DIR} ${GENERATED_DIR})
add_dependencies(app tank_temperature_signals)

# product_temperature.c calls through to pt100.c's sqrtf(); native_sim's
# toolchain does not always pull libm in on its own.
target_link_libraries(app PRIVATE m)
