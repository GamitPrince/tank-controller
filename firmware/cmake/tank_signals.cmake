# Generate every Phase 1 signal table the firmware application needs (S-060).
#
# The signal list in interfaces/ is the contract (ADR-0004 decision 9), so the
# tables are generated from it at build time and never committed. Each module
# test generates only its own table; the application and its test need all
# five, so this helper keeps the commands in one place.
#
# Usage, after find_package(Zephyr):
#   include(${FIRMWARE_DIR}/cmake/tank_signals.cmake)
#   tank_generate_signal_tables(app ${CMAKE_CURRENT_BINARY_DIR}/generated)

function(tank_generate_signal_table target out_dir header script)
  set(firmware_dir ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/..)
  set(signal_list ${firmware_dir}/../interfaces/signals-v1.yaml)
  set(output ${out_dir}/${header})

  add_custom_command(
    OUTPUT ${output}
    COMMAND ${PYTHON_EXECUTABLE} ${firmware_dir}/scripts/${script}
            --signals ${signal_list}
            --output ${output}
            ${ARGN}
    DEPENDS ${firmware_dir}/scripts/${script} ${signal_list}
    COMMENT "Generating ${header} from signals-v1.yaml"
    VERBATIM
  )
  target_sources(${target} PRIVATE ${output})
endfunction()

function(tank_generate_signal_tables target out_dir)
  tank_generate_signal_table(${target} ${out_dir} tank_safety_signals.h
                             gen_safety_signals.py --story P1-05)
  tank_generate_signal_table(${target} ${out_dir} tank_alarm_signals.h
                             gen_safety_signals.py --story P1-09)
  tank_generate_signal_table(${target} ${out_dir} tank_equipment_status_signals.h
                             gen_equipment_status_signals.py)
  tank_generate_signal_table(${target} ${out_dir} tank_level_signals.h
                             gen_level_signals.py)
  tank_generate_signal_table(${target} ${out_dir} tank_temperature_signals.h
                             gen_temperature_signals.py)
  target_include_directories(${target} PRIVATE ${out_dir})
endfunction()
