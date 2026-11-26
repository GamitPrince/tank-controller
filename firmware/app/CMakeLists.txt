# The Tank-AI FRDM-MCXN947 firmware application (S-060). Until the EE's board
# overlay and pin mapping exist it is built for native_sim only, in CI.
cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(tank_firmware)

set(FIRMWARE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/..)
include(${FIRMWARE_DIR}/cmake/tank_app_sources.cmake)

target_sources(app PRIVATE src/main.c)
tank_add_app_sources(app ${CMAKE_CURRENT_BINARY_DIR}/generated)
