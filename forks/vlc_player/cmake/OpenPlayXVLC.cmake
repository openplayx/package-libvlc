# The VLC core and its plugins are built from the pinned recipe. FFmpeg is
# packaged exclusively by openplayx_ffmpeg, so no system/downloaded VLC is used.
if(WIN32)
  # CMake REALPATH retains Flutter's Windows junction path. Resolve the real
  # package before walking above forks/vlc_player to its owning repository.
  find_package(Python3 REQUIRED COMPONENTS Interpreter)
  execute_process(
    COMMAND "${Python3_EXECUTABLE}" -X utf8 -I -c
      "from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve().as_posix())"
      "${CMAKE_CURRENT_LIST_DIR}/.."
    RESULT_VARIABLE OPX_VLC_PATH_RESULT
    OUTPUT_VARIABLE OPX_VLC_PLUGIN_DIR
    ERROR_VARIABLE OPX_VLC_PATH_ERROR
    OUTPUT_STRIP_TRAILING_WHITESPACE
    ENCODING UTF-8)
  if(NOT OPX_VLC_PATH_RESULT EQUAL 0)
    message(FATAL_ERROR "Resolving VLC package path failed: ${OPX_VLC_PATH_ERROR}")
  endif()
else()
  get_filename_component(OPX_VLC_PLUGIN_DIR "${CMAKE_CURRENT_LIST_DIR}/.." REALPATH)
endif()
get_filename_component(OPX_VLC_ROOT "${OPX_VLC_PLUGIN_DIR}/../.." ABSOLUTE)
if(WIN32)
  set(OPX_VLC_TARGET windows-x86_64)
elseif(CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64|arm64")
  set(OPX_VLC_TARGET linux-arm64)
else()
  set(OPX_VLC_TARGET linux-x86_64)
endif()
if(NOT EXISTS "${OPX_VLC_ROOT}/tool/build_libvlc.sh")
  message(FATAL_ERROR "VLC package build entry point is missing: ${OPX_VLC_ROOT}")
endif()
find_program(OPX_VLC_BASH bash REQUIRED)
execute_process(COMMAND "${OPX_VLC_BASH}" "${OPX_VLC_ROOT}/tool/build_libvlc.sh" "${OPX_VLC_TARGET}"
  RESULT_VARIABLE OPX_VLC_RESULT)
if(NOT OPX_VLC_RESULT EQUAL 0)
  message(FATAL_ERROR "Building shared-FFmpeg VLC failed: tool/build_libvlc.sh ${OPX_VLC_TARGET}")
endif()
set(OPX_VLC_PREFIX "${OPX_VLC_ROOT}/third_party/libvlc/${OPX_VLC_TARGET}")
add_library(openplayx_vlc SHARED IMPORTED)
if(WIN32)
  set_target_properties(openplayx_vlc PROPERTIES
    IMPORTED_LOCATION "${OPX_VLC_PREFIX}/bin/libvlc.dll"
    IMPORTED_IMPLIB "${OPX_VLC_PREFIX}/lib/libvlc.lib"
    INTERFACE_INCLUDE_DIRECTORIES "${OPX_VLC_PREFIX}/include")
  file(GLOB OPX_VLC_RUNTIME_LIBS "${OPX_VLC_PREFIX}/bundle/*.dll")
else()
  set_target_properties(openplayx_vlc PROPERTIES
    IMPORTED_LOCATION "${OPX_VLC_PREFIX}/lib/libvlc.so"
    INTERFACE_INCLUDE_DIRECTORIES "${OPX_VLC_PREFIX}/include")
  file(GLOB OPX_VLC_RUNTIME_LIBS "${OPX_VLC_PREFIX}/bundle/lib*.so*")
endif()
