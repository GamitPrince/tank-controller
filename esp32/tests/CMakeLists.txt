# Host build of the ESP32 logic and its Unity tests (S-047, ADR-0006
# decision 3). ESP-IDF is not needed: the code under test is standard C.
# esp32/ci.sh configures this with UNITY_DIR pointing at the fetched Unity.
cmake_minimum_required(VERSION 3.20)
project(tank_esp32_host_tests C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

set(UNITY_DIR "" CACHE PATH "Unity source tree (fetched by esp32/ci.sh)")
if(NOT EXISTS "${UNITY_DIR}/src/unity.c")
  message(FATAL_ERROR "Set UNITY_DIR to a Unity checkout; esp32/ci.sh does this.")
endif()

set(ESP32_DIR ${CMAKE_CURRENT_SOURCE_DIR}/..)
# The shared link library (ADR-0004 decision 5) stays in the FRDM tree for
# now; both boards compile the same files.
set(LINK_DIR ${ESP32_DIR}/../firmware/src/communications)

set(STRICT_FLAGS -Wall -Wextra -Wpedantic -Werror)
set(COVERAGE_FLAGS --coverage -O0)

add_library(unity STATIC ${UNITY_DIR}/src/unity.c)
target_include_directories(unity PUBLIC ${UNITY_DIR}/src)

add_library(link_shared STATIC
  ${LINK_DIR}/link_frame.c
  ${LINK_DIR}/link_receiver.c
  ${LINK_DIR}/link_sender.c
)
target_include_directories(link_shared PUBLIC ${LINK_DIR})
target_compile_options(link_shared PRIVATE ${STRICT_FLAGS})

add_library(link_endpoint STATIC ${ESP32_DIR}/components/link_endpoint/link_endpoint.c)
target_include_directories(link_endpoint PUBLIC ${ESP32_DIR}/components/link_endpoint/include)
target_link_libraries(link_endpoint PUBLIC link_shared)
target_compile_options(link_endpoint PRIVATE ${STRICT_FLAGS} ${COVERAGE_FLAGS})
target_link_options(link_endpoint PUBLIC --coverage)

enable_testing()
foreach(name test_link_endpoint test_link_e2e)
  add_executable(${name} ${name}.c)
  target_link_libraries(${name} PRIVATE link_endpoint unity)
  target_compile_options(${name} PRIVATE ${STRICT_FLAGS})
  add_test(NAME ${name} COMMAND ${name})
endforeach()
