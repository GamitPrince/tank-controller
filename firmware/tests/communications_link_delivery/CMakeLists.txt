# ztest application for delivery confirmation on the FRDM-to-ESP32 UART link
# (S-043), built by Twister on native_sim.
cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(communications_link_delivery)

# The shared link library (S-056, ADR-0003 amendment 1), also built for the ESP32.
set(LINK_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../../shared/link-protocol)

target_sources(app PRIVATE
  src/main.c
  src/receiver.c
  ${LINK_DIR}/link_frame.c
  ${LINK_DIR}/link_receiver.c
  ${LINK_DIR}/link_sender.c
)

target_include_directories(app PRIVATE ${LINK_DIR})
