#!/usr/bin/env bash
# Build the pinned Android Java/JNI engine against shared package-ffmpeg.
# targets/ABIs: android-arm64-v8a android-armeabi-v7a android-x86_64
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
source "$root/tool/vlc-sources.env"
source "$root/tool/native_common.sh"
opx_lock "$root/third_party/.lock-android-build"
export OPX_FFMPEG_PACKAGE="$(cd "${OPX_FFMPEG_PACKAGE:-$root/../ffmpeg-package}" && pwd)"
export ANDROID_NDK_HOME="${ANDROID_NDK_HOME:?set ANDROID_NDK_HOME}"
export OPX_BUILD_JOBS="${OPX_BUILD_JOBS:-$(getconf _NPROCESSORS_ONLN)}"
bash "$root/tool/prepare_libvlc_android.sh"
abis=("$@")
[ ${#abis[@]} -gt 0 ] || abis=(arm64-v8a armeabi-v7a x86_64)
for abi in "${abis[@]}"; do
  case "$abi" in arm64-v8a|armeabi-v7a|x86_64) ;; *) echo "Unsupported ABI: $abi" >&2; exit 1 ;; esac
  target="android-$abi"
  opx_ensure_ffmpeg "$target"
  export OPX_FFMPEG_PREFIX="$OPX_FFMPEG_PACKAGE/third_party/ffmpeg/$target"
  prefix="$root/third_party/libvlc/$target"
  jni="$root/third_party/libvlcjni"
  fingerprint="$(bash "$root/tool/build_fingerprint.sh" "$target")"
  if [ "$(cat "$prefix/BUILD_FINGERPRINT" 2>/dev/null || true)" != "$fingerprint" ]; then
    mkdir -p "$root/build"
    log="$root/build/libvlc-$target.log"
    pkg_config_bin="$(command -v pkg-config)"
    echo "Building Android libVLC $abi (log: $log)"
    if ! (cd "$jni" && env -i PATH="$PATH" HOME="$HOME" \
      ANDROID_NDK="$ANDROID_NDK_HOME" OPX_FFMPEG_PREFIX="$OPX_FFMPEG_PREFIX" \
      OPX_FFMPEG_PKGCONFIG="$OPX_FFMPEG_PKGCONFIG" OPX_BUILD_JOBS="$OPX_BUILD_JOBS" \
      MAKEFLAGS="-j$OPX_BUILD_JOBS" \
      ACLOCAL_PATH="$(dirname "$(dirname "$pkg_config_bin")")/share/aclocal" \
      bash buildsystem/compile-libvlc.sh -a "$abi" --release --license g) > "$log" 2>&1; then
      tail -60 "$log" >&2
      exit 1
    fi
    rm -rf "$prefix"
    mkdir -p "$prefix/lib" "$prefix/jniLibs/$abi"
    # Keep unstripped libraries for ABI/static-copy verification; Gradle strips
    # the APK's copies and keeps debug symbols through its normal pipeline.
    cp "$jni/libvlc/jni/obj/local/$abi/"*.so "$prefix/lib/"
    if [ -f "$jni/libvlc/jni/libs/$abi/libc++_shared.so" ]; then
      cp "$jni/libvlc/jni/libs/$abi/libc++_shared.so" "$prefix/lib/"
    fi
    cp "$prefix/lib/"*.so "$prefix/jniLibs/$abi/"
    printf 'libvlcjni=%s\nvlc=%s\nffmpeg_prefix=%s\n' "$LIBVLCJNI_REVISION" "$ANDROID_VLC_REVISION" "$OPX_FFMPEG_PREFIX" > "$prefix/BUILDINFO"
    python3 "$root/tool/verify_libvlc.py" "$target" "$prefix" "$OPX_FFMPEG_PREFIX"
    printf '%s\n' "$fingerprint" > "$prefix/BUILD_FINGERPRINT"
  else
    python3 "$root/tool/verify_libvlc.py" "$target" "$prefix" "$OPX_FFMPEG_PREFIX"
  fi
done
# Match the upstream AAR's runtime resources without importing its binaries.
assets="$jni/libvlc/assets"
mkdir -p "$assets/lua"
[ ! -d "$jni/vlc/share/hrtfs" ] || cp -R "$jni/vlc/share/hrtfs" "$assets/"
for kind in playlist meta modules; do
  [ ! -d "$jni/vlc/share/lua/$kind" ] || cp -R "$jni/vlc/share/lua/$kind" "$assets/lua/"
done
