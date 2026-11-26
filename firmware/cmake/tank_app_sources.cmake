# The firmware sources the application is built from (S-060), shared by the
# application in firmware/app/ and its test in firmware/tests/app_tank_app/ so
# the two cannot drift apart.
#
# Usage, after find_package(Zephyr):
#   include(${FIRMWARE_DIR}/cmake/tank_app_sources.cmake)
#   tank_add_app_sources(app ${CMAKE_CURRENT_BINARY_DIR}/generated)

include(${CMAKE_CURRENT_LIST_DIR}/tank_signals.cmake)

function(tank_add_app_sources target generated_dir)
  set(src ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/../src)
  set(link ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/../../shared/link-protocol)

  target_sources(${target} PRIVATE
    ${src}/app/tank_app.c
    ${src}/app/device_id.c
    ${src}/communications/uplink_service.c
    ${src}/communications/log_forwarder.c
    ${src}/communications/uplink.c
    ${src}/hardware/esp32_uart.c
    ${src}/record/record_cbor.c
    ${link}/link_frame.c
    ${link}/link_sender.c
    ${src}/record/scan_service.c
    ${src}/record/scan_builder.c
    ${src}/record/scan_codec.c
    ${src}/record/flash_log.c
    ${src}/record/boot_time.c
    ${src}/safety/level_switch.c
    ${src}/safety/level_switch_config.c
    ${src}/safety/alarm_input_config.c
    ${src}/measurement/equipment_status_config.c
    ${src}/measurement/loop_level.c
    ${src}/measurement/loop_level_config.c
    ${src}/measurement/product_temperature.c
    ${src}/measurement/product_temperature_config.c
    ${src}/measurement/pt100.c
    ${src}/hardware/ad4111.c
    ${src}/hardware/max31865.c
  )
  target_include_directories(${target} PRIVATE
    ${src}/app
    ${src}/record
    ${src}/safety
    ${src}/measurement
    ${src}/hardware
    ${src}/communications
    ${link}
  )
  tank_generate_signal_tables(${target} ${generated_dir})

  # pt100.c uses sqrtf(); native_sim's toolchain does not always pull libm in.
  target_link_libraries(${target} PRIVATE m)
endfunction()
