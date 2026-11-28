#!/usr/bin/env bash
# Build the desktop VLC core and plugins against package-ffmpeg's shared libs.
# targets: linux-arm64 linux-x86_64 windows-x86_64 (native MSYS2/MinGW-w64)
# Android targets: android-arm64-v8a android-armeabi-v7a android-x86_64.
# Apple is built by ensure_vlckit_apple.sh.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
source "$root/tool/vlc-sources.env"
source "$root/tool/native_common.sh"
target="${1:?usage: build_libvlc.sh linux-arm64|linux-x86_64|windows-x86_64}"
case "$target" in
  android-*) exec bash "$root/tool/ensure_libvlc_android.sh" "${target#android-}" ;;
esac
case "$target:$(uname -s)" in
  linux-arm64:Linux|linux-x86_64:Linux) host="$(gcc -dumpmachine)" ;;
  windows-x86_64:MINGW*|windows-x86_64:MSYS*) host=x86_64-w64-mingw32 ;;
  *) echo "Build $target on its matching Linux or MSYS2 host" >&2; exit 1 ;;
esac
case "$target:$(uname -m)" in
  linux-arm64:aarch64|linux-arm64:arm64|linux-x86_64:x86_64|windows-x86_64:*) ;;
  *) echo "Target does not match build host architecture: $target" >&2; exit 1 ;;
esac
export OPX_FFMPEG_PACKAGE="$(cd "${OPX_FFMPEG_PACKAGE:-$root/../ffmpeg-package}" && pwd)"
export OPX_BUILD_JOBS="${OPX_BUILD_JOBS:-$(getconf _NPROCESSORS_ONLN)}"
opx_lock "$root/third_party/.lock-$target"
opx_ensure_ffmpeg "$target"
# VLC 3.x and its legacy C dependencies predate C23's prototype rules.
# GCC 15+ defaults to C23, which breaks e.g. GNU regex 0.13's declarations.
if [[ "$target" = windows-* ]]; then
  export CFLAGS="${CFLAGS:--O2 -g} -std=gnu17"
fi
ffmpeg="$OPX_FFMPEG_PACKAGE/third_party/ffmpeg/$target"
prefix="$root/third_party/libvlc/$target"
fingerprint="$(bash "$root/tool/build_fingerprint.sh" "$target")"
if [ "$(cat "$prefix/BUILD_FINGERPRINT" 2>/dev/null || true)" = "$fingerprint" ]; then
  python3 "$root/tool/verify_libvlc.py" "$target" "$prefix" "$ffmpeg"
  exit 0
fi
src="${OPX_VLC_SOURCE_DIR:-$root/third_party/vlc-desktop/$target}"
opx_checkout https://github.com/videolan/vlc.git "$VLC_REVISION" "$src"
python3 "$root/tool/patch_vlc_contrib.py" "$src"
export PATH="$src/extras/tools/build/bin:$PATH"
pkg_config_bin="$(command -v pkg-config)"
export ACLOCAL_PATH="$(dirname "$(dirname "$pkg_config_bin")")/share/aclocal${ACLOCAL_PATH:+:$ACLOCAL_PATH}"
(cd "$src/extras/tools" && ./bootstrap && make -j"$OPX_BUILD_JOBS")
[ -f "$src/configure" ] || (cd "$src" && ./bootstrap)
deps="$src/contrib/opx-$target"
contrib="$src/contrib/$host"
mkdir -p "$deps"
# Keep VLC's playback dependencies, excluding standalone interfaces and the
# codec libraries already encapsulated by the shared FFmpeg build.
contrib_args=(--disable-ffmpeg --disable-postproc --disable-qt --disable-qtsvg
  --disable-sdl --disable-SDL_image --disable-skins2 --disable-gettext
  --disable-x264 --disable-x265 --disable-x262 --disable-chromaprint
  --disable-vncclient --disable-vncserver --disable-sparkle --disable-growl
  --disable-breakpad --disable-goom --disable-ncurses --disable-mad
  --disable-mpcdec --disable-libmpeg2 --disable-lua --disable-luac)
native_build=()
[[ "$target" != linux-* ]] || native_build=(--build="$host")
(cd "$deps" && ../bootstrap "${native_build[@]}" --host="$host" --prefix="$contrib" "${contrib_args[@]}")
printf 'PKG_CONFIG_PATH := %s\n' "$OPX_FFMPEG_PKGCONFIG" > "$deps/config.mak"
# Check one dependency at a time, keeping parallel compilation inside each
# package. The checker invalidates only changed recipes and their dependents.
dependency_args=(--directory "$deps" --report "${OPX_VLC_DEPENDENCY_REPORT:-$root/build/dependency-checks/$target}"
  --jobs "$OPX_BUILD_JOBS")
if [ -n "${OPX_VLC_SOURCE_CACHE_KEY:-}" ]; then
  dependency_args+=(--cache-key "$OPX_VLC_SOURCE_CACHE_KEY")
fi
python3 -X utf8 -I "$root/tool/check_vlc_contrib.py" "${dependency_args[@]}"
# Never retain a previous contrib build's static FFmpeg or headers.
rm -f "$contrib"/lib/libav*.a "$contrib"/lib/libsw*.a
rm -f "$contrib"/lib/pkgconfig/libav*.pc "$contrib"/lib/pkgconfig/libsw*.pc
rm -rf "$contrib"/include/libav* "$contrib"/include/libsw*
export PKG_CONFIG_PATH="$contrib/lib/pkgconfig:$OPX_FFMPEG_PKGCONFIG"
if [[ "$target" = linux-* ]]; then
  # Native desktop SDKs (PulseAudio/ALSA/GTK) are system dependencies; FFmpeg
  # always resolves first from the owner's prefix above.
  export PKG_CONFIG_LIBDIR="$PKG_CONFIG_PATH:$(pkg-config --variable pc_path pkg-config)"
else
  export PKG_CONFIG_LIBDIR="$PKG_CONFIG_PATH"
fi
build="${OPX_VLC_BUILD_DIR:-$root/third_party/vlc-build/$target}"
mkdir -p "$build"
flags=(--host="$host" --prefix="$prefix" --with-contrib="$contrib"
  --enable-shared --disable-static --disable-vlc --disable-nls --disable-dbus
  --disable-qt --disable-skins2 --disable-ncurses --disable-lua --disable-chromaprint --disable-gst-decode
  --disable-x264 --disable-x265 --disable-postproc --enable-avcodec --enable-avformat
  --enable-swscale --disable-update-check --disable-notify)
# Retain objects when only a contrib archive changes, but reconfigure/recompile
# when the compiler, flags, source revision or configure arguments change.
compile_key="$(python3 - "$VLC_REVISION" "${flags[@]}" <<'PYKEY'
import hashlib, json, os, subprocess, sys
inputs = {'arguments': sys.argv[1:], 'environment': {key: os.environ.get(key, '') for key in (
    'CC', 'CXX', 'BUILDCC', 'CFLAGS', 'CXXFLAGS', 'CPPFLAGS', 'LDFLAGS',
    'FLUIDLITE_CFLAGS', 'FLUIDSYNTH_CFLAGS', 'AVCODEC_CFLAGS', 'AVFORMAT_CFLAGS',
    'AVUTIL_CFLAGS', 'SWSCALE_CFLAGS')}}
for compiler in ('gcc', 'g++'):
    inputs[compiler] = subprocess.check_output([compiler, '--version'], text=True).splitlines()[0]
print(hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest())
PYKEY
)"
if [ "$(cat "$build/.opx-compile-key" 2>/dev/null || true)" != "$compile_key" ]; then
  rm -rf "$build"
  mkdir -p "$build"
else
  # Libtool's -lfoo dependencies do not track changes to static contrib archives.
  # Relink plugins/core using the existing object files after package changes.
  find "$build" -name '*.la' -type f -delete
fi
if [[ "$target" = windows-* ]]; then
  # Resolve the C++ and pthread runtimes statically, while keeping FFmpeg
  # shared. A global -static would select another FFmpeg's static archives.
  runtime="$build/runtime"
  mkdir -p "$runtime"
  for lib in winpthread stdc++; do cp "$(gcc -print-file-name=lib$lib.a)" "$runtime/"; done
  cp "$runtime/libwinpthread.a" "$runtime/libpthread.a"
  export LDFLAGS="-L$(cygpath -m "$runtime") -static-libgcc -static-libstdc++"
  flags+=(--disable-macosx --disable-sdl-image)
fi
(cd "$build" && "$src/configure" "${flags[@]}")
printf '%s\n' "$compile_key" > "$build/.opx-compile-key"
(cd "$build" && make -j"$OPX_BUILD_JOBS")
rm -rf "$prefix"
(cd "$build" && make install)
python3 "$root/tool/stage_libvlc.py" "$target" "$prefix" "$src"
python3 "$root/tool/verify_libvlc.py" "$target" "$prefix" "$ffmpeg"
printf 'vlc=%s\nffmpeg_prefix=%s\ntarget=%s\n' "$VLC_REVISION" "$ffmpeg" "$target" > "$prefix/BUILDINFO"
printf '%s\n' "$fingerprint" > "$prefix/BUILD_FINGERPRINT"
