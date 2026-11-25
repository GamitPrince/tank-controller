# ztest application for delivery confirmation on the FRDM-to-ESP32 UART link
# (S-043), built by Twister on native_sim.
cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(communications_link_delivery)

set(COMMS_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../src/communications)

target_sources(app PRIVATE
  src/main.c
  ${COMMS_DIR}/link_frame.c
  ${COMMS_DIR}/link_sender.c
)

target_include_directories(app PRIVATE ${COMMS_DIR})
