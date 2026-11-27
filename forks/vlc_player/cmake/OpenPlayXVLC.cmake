# The VLC core and its plugins are built from the pinned recipe. FFmpeg is
# packaged exclusively by openplayx_ffmpeg, so no system/downloaded VLC is used.
get_filename_component(OPX_VLC_PLUGIN_DIR "${CMAKE_CURRENT_LIST_DIR}/.." REALPATH)
get_filename_component(OPX_VLC_ROOT "${OPX_VLC_PLUGIN_DIR}/../.." ABSOLUTE)
if(WIN32)
  set(OPX_VLC_TARGET windows-x86_64)
elseif(CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64|arm64")
  set(OPX_VLC_TARGET linux-arm64)
else()
  set(OPX_VLC_TARGET linux-x86_64)
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
