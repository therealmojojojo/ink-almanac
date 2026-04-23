cmake_minimum_required(VERSION 3.20)
project(inkplate_firmware_sim LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Debug)
endif()

add_compile_options(
  -Wall -Wextra -Wpedantic -Werror
  -Wshadow -Wconversion -Wsign-conversion
  -fno-omit-frame-pointer
)

# Workaround: on macOS with CommandLineTools only (no full Xcode), clang
# searches for libc++ under `usr/bin/../include/c++/v1`, which doesn't exist.
# The headers actually live under the SDK. Point clang there explicitly if
# the expected path is empty.
if(APPLE)
  execute_process(COMMAND xcrun --show-sdk-path
                  OUTPUT_VARIABLE _macos_sdk
                  OUTPUT_STRIP_TRAILING_WHITESPACE)
  if(_macos_sdk AND EXISTS "${_macos_sdk}/usr/include/c++/v1/cstdint")
    add_compile_options(-nostdinc++ -isystem "${_macos_sdk}/usr/include/c++/v1")
  endif()
endif()

#
# doctest — header-only. Vendored under third_party/doctest.
#
set(DOCTEST_DIR ${CMAKE_SOURCE_DIR}/test/third_party/doctest)

add_library(doctest INTERFACE)
target_include_directories(doctest INTERFACE ${DOCTEST_DIR})

#
# Firmware sources. The real HAL and main loop live under firmware/src/ and
# are added by `add-device-firmware`. This native build only pulls in what
# exists; when firmware sources land, they're picked up automatically.
#
file(GLOB_RECURSE FIRMWARE_SRC CONFIGURE_DEPENDS
  ${CMAKE_SOURCE_DIR}/src/*.cpp
)

#
# Simulator: HAL interfaces, mock implementations, harness, scenarios.
#
file(GLOB_RECURSE SIM_SRC CONFIGURE_DEPENDS
  ${CMAKE_SOURCE_DIR}/test/hal/mock/*.cpp
  ${CMAKE_SOURCE_DIR}/test/harness/*.cpp
  ${CMAKE_SOURCE_DIR}/test/scenarios/*.cpp
  ${CMAKE_SOURCE_DIR}/test/power/*.cpp
)

add_executable(firmware_sim
  test/main.cpp
  ${SIM_SRC}
  ${FIRMWARE_SRC}
)

target_include_directories(firmware_sim PRIVATE
  ${CMAKE_SOURCE_DIR}/include
  ${CMAKE_SOURCE_DIR}/src
  ${CMAKE_SOURCE_DIR}/test
)

target_link_libraries(firmware_sim PRIVATE doctest)

enable_testing()
add_test(NAME firmware_sim COMMAND firmware_sim)
