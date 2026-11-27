# The Flutter tooling requires that developers have a version of Visual Studio
# installed that includes CMake 3.14 or later. You should not increase this
# version, as doing so will cause the plugin to fail to compile for some
# customers of the plugin.
cmake_minimum_required(VERSION 3.14)

# Project-level configuration.
set(PROJECT_NAME "vlc_player")
project(${PROJECT_NAME} LANGUAGES CXX)

# Explicitly opt in to modern CMake behaviors to avoid warnings with recent
# versions of CMake.
cmake_policy(VERSION 3.14...3.25)

# This value is used when generating builds using this plugin, so it must
# not be changed
set(PLUGIN_NAME "vlc_player_plugin")

# Any new source files that you add to the plugin should be added here.
list(APPEND PLUGIN_SOURCES
  "../src/native/vlc_player_core.cc"
  "../src/native/vlc_player_core.h"
  "../src/native/vlc_player_types.h"
  "vlc_player_plugin.cpp"
  "vlc_player_plugin.h"
)

# Define the plugin library target. Its name must not be changed (see comment
# on PLUGIN_NAME above).
add_library(${PLUGIN_NAME} SHARED
  "include/vlc_player/vlc_player_plugin_c_api.h"
  "vlc_player_plugin_c_api.cpp"
  ${PLUGIN_SOURCES}
)

# Apply a standard set of build settings that are configured in the
# application-level CMakeLists.txt. This can be removed for plugins that want
# full control over build settings.
apply_standard_settings(${PLUGIN_NAME})

# Symbols are hidden by default to reduce the chance of accidental conflicts
# between plugins. This should not be removed; any symbols that should be
# exported should be explicitly exported with the FLUTTER_PLUGIN_EXPORT macro.
set_target_properties(${PLUGIN_NAME} PROPERTIES
  CXX_VISIBILITY_PRESET hidden)
target_compile_definitions(${PLUGIN_NAME} PRIVATE FLUTTER_PLUGIN_IMPL)

# Source include directories and library dependencies. Add any plugin-specific
# dependencies here.
target_include_directories(${PLUGIN_NAME} INTERFACE
  "${CMAKE_CURRENT_SOURCE_DIR}/include")
target_link_libraries(${PLUGIN_NAME} PRIVATE flutter flutter_wrapper_plugin)

if(NOT CMAKE_SIZEOF_VOID_P EQUAL 8)
  message(FATAL_ERROR "vlc_player currently supports Windows x64 builds only.")
endif()

include("${CMAKE_CURRENT_SOURCE_DIR}/../cmake/OpenPlayXVLC.cmake")
set(VLC_PLAYER_RUNTIME_DIR "${OPX_VLC_PREFIX}")
set(VLC_PLAYER_RUNTIME_DLLS ${OPX_VLC_RUNTIME_LIBS})
target_include_directories(${PLUGIN_NAME} PRIVATE
  "${CMAKE_CURRENT_SOURCE_DIR}/../src/native"
  "${CMAKE_CURRENT_SOURCE_DIR}/../third_party/libvlcpp")
target_link_libraries(${PLUGIN_NAME} PRIVATE openplayx_vlc)
set(vlc_player_bundled_libraries ${OPX_VLC_RUNTIME_LIBS} PARENT_SCOPE)
if(DEFINED BINARY_NAME)
  add_custom_target(${PLUGIN_NAME}_copy_plugins ALL
    COMMAND "${CMAKE_COMMAND}" -E copy_directory "${OPX_VLC_PREFIX}/lib/vlc/plugins"
      "$<TARGET_FILE_DIR:${BINARY_NAME}>/plugins")
endif()

# === Tests ===
# These unit tests can be run from a terminal after building the example, or
# from Visual Studio after opening the generated solution file.

# Only enable test builds when building the example (which sets this variable)
# so that plugin clients aren't building the tests.
if (${include_${PROJECT_NAME}_tests})
set(TEST_RUNNER "${PROJECT_NAME}_test")
enable_testing()

# Add the Google Test dependency.
include(FetchContent)
FetchContent_Declare(
  googletest
  URL https://github.com/google/googletest/archive/refs/tags/v1.17.0.zip
  DOWNLOAD_EXTRACT_TIMESTAMP TRUE
)
# Prevent overriding the parent project's compiler/linker settings
set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
# Disable install commands for gtest so it doesn't end up in the bundle.
set(INSTALL_GTEST OFF CACHE BOOL "Disable installation of googletest" FORCE)
FetchContent_MakeAvailable(googletest)

# The plugin's C API is not very useful for unit testing, so build the sources
# directly into the test binary rather than using the DLL.
add_executable(${TEST_RUNNER}
  test/vlc_player_plugin_test.cpp
  ${PLUGIN_SOURCES}
)
apply_standard_settings(${TEST_RUNNER})
target_compile_definitions(${TEST_RUNNER} PRIVATE VLC_PLAYER_TESTING)
target_include_directories(${TEST_RUNNER} PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
target_include_directories(${TEST_RUNNER} PRIVATE
  "${CMAKE_CURRENT_SOURCE_DIR}/../src/native"
  "${CMAKE_CURRENT_SOURCE_DIR}/../third_party/libvlcpp"
  "${VLC_PLAYER_RUNTIME_DIR}/include")
target_link_libraries(${TEST_RUNNER} PRIVATE flutter_wrapper_plugin)
target_link_libraries(${TEST_RUNNER} PRIVATE
  openplayx_vlc)
target_link_libraries(${TEST_RUNNER} PRIVATE gtest_main gmock)
# flutter_wrapper_plugin has link dependencies on the Flutter DLL.
add_custom_command(TARGET ${TEST_RUNNER} POST_BUILD
  COMMAND ${CMAKE_COMMAND} -E copy_if_different
  "${FLUTTER_LIBRARY}" $<TARGET_FILE_DIR:${TEST_RUNNER}>
)
foreach(vlc_player_runtime_dll ${VLC_PLAYER_RUNTIME_DLLS})
  add_custom_command(TARGET ${TEST_RUNNER} POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
    "${vlc_player_runtime_dll}" $<TARGET_FILE_DIR:${TEST_RUNNER}>
  )
endforeach()
foreach(vlc_player_runtime_directory plugins)
  if(EXISTS "${VLC_PLAYER_RUNTIME_DIR}/lib/vlc/${vlc_player_runtime_directory}")
    add_custom_command(TARGET ${TEST_RUNNER} POST_BUILD
      COMMAND "${CMAKE_COMMAND}" -E copy_directory
      "${VLC_PLAYER_RUNTIME_DIR}/lib/vlc/${vlc_player_runtime_directory}"
      "$<TARGET_FILE_DIR:${TEST_RUNNER}>/${vlc_player_runtime_directory}")
  endif()
endforeach()

# Enable automatic test discovery.
include(GoogleTest)
gtest_discover_tests(${TEST_RUNNER})
endif()
