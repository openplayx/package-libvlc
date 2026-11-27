#!/usr/bin/env bash
# Build VLCKit from pinned sources against package-ffmpeg's shared libraries.
# Called at pod install, before CocoaPods enumerates vendored frameworks.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
source "$root/tool/vlc-sources.env"
platform="${1:?usage: ensure_vlckit_apple.sh macos|ios|tvos}"
case "$platform" in
  macos) kit=VLCKit; args=(-x); targets='macos-arm64 macos-x86_64' ;;
  ios) kit=MobileVLCKit; args=(-f); targets='ios-arm64 ios-sim-arm64 ios-sim-x86_64' ;;
  tvos) kit=TVVLCKit; args=(-t -f); targets='tvos-arm64 tvos-sim-arm64' ;;
  *) echo "Unsupported platform: $platform" >&2; exit 1 ;;
esac
export OPX_FFMPEG_PACKAGE="$(cd "${OPX_FFMPEG_PACKAGE:-$root/../ffmpeg-package}" && pwd)"
bash "$OPX_FFMPEG_PACKAGE/tool/ensure_ffmpeg_apple.sh" "$platform"
mkdir -p "$root/third_party"
lock="$root/third_party/.lock-vlckit"
until mkdir "$lock" 2>/dev/null; do
  holder="$(cat "$lock/pid" 2>/dev/null || true)"
  if [ -n "$holder" ] && ! kill -0 "$holder" 2>/dev/null; then rm -rf "$lock"; continue; fi
  sleep 2
done
echo $$ > "$lock/pid"
trap 'rm -rf "$lock"' EXIT
out="$root/$platform/Frameworks"
fingerprint="$( { cat "$root/tool/vlc-sources.env" "$root/tool/patch_vlckit.py" "$0" "$root/tool/verify_vlckit.py"; for p in "$root"/tool/patches/*.patch; do [ ! -f "$p" ] || cat "$p"; done; for t in $targets; do cat "$OPX_FFMPEG_PACKAGE/third_party/ffmpeg/$t/BUILD_FINGERPRINT"; done; } | shasum -a 256 | cut -d ' ' -f 1)"
if [ -f "$out/.fingerprint" ] && [ "$(cat "$out/.fingerprint")" = "$fingerprint" ] && [ -d "$out/$kit.xcframework" ]; then
  python3 "$root/tool/verify_vlckit.py" "$out/$kit.xcframework"
  exit 0
fi
checkout() {
  local url="$1" revision="$2" dir="$3"
  if [ ! -d "$dir/.git" ]; then
    git init "$dir"
    git -C "$dir" remote add origin "$url"
  fi
  if ! git -C "$dir" cat-file -e "$revision^{commit}" 2>/dev/null; then
    git -C "$dir" fetch --depth 1 origin "$revision"
  fi
  if [ "$(git -C "$dir" rev-parse HEAD 2>/dev/null || true)" != "$revision" ]; then
    # Only managed build caches live here. A revision change invalidates
    # generated configure/Makefiles as well as tracked recipe patches.
    git -C "$dir" checkout --force --detach "$revision"
    git -C "$dir" clean -fdx
  fi
}
src="$root/third_party/vlckit"
checkout https://github.com/videolan/vlckit.git "$VLCKIT_REVISION" "$src"
checkout https://github.com/videolan/vlc.git "$VLC_REVISION" "$src/libvlc/vlc"
# This is a managed source cache, never a developer checkout. Apply the whole
# upstream series once: later patches can change earlier patches' context.
patch_stamp="$src/libvlc/vlc/.opx-patches"
patch_hash="$( { echo "$VLCKIT_REVISION $VLC_REVISION"; cat "$root"/tool/patches/*.patch 2>/dev/null || true; } | shasum -a 256 | cut -d ' ' -f 1)"
if [ "$(cat "$patch_stamp" 2>/dev/null || true)" != "$patch_hash" ]; then
  git -C "$src/libvlc/vlc" reset --hard "$VLC_REVISION"
  git -C "$src/libvlc/vlc" clean -fd
  for patch in "$src"/libvlc/patches/*.patch "$root"/tool/patches/*.patch; do
    [ -f "$patch" ] || continue
    git -C "$src/libvlc/vlc" apply "$patch"
  done
  printf '%s\n' "$patch_hash" > "$patch_stamp"
fi
# VLC's legacy gas download URL is retired. Supply the pinned FFmpeg helper
# directly; arm64 deinterlacing assembly still needs it with Apple's assembler.
gas="$root/third_party/gas-preprocessor.pl"
if [ ! -f "$gas" ] || [ "$(shasum -a 256 "$gas" | cut -d ' ' -f 1)" != "$GAS_PREPROCESSOR_SHA256" ]; then
  curl -fsSL --retry 3 "https://raw.githubusercontent.com/FFmpeg/gas-preprocessor/$GAS_PREPROCESSOR_REVISION/gas-preprocessor.pl" -o "$gas.part"
  [ "$(shasum -a 256 "$gas.part" | cut -d ' ' -f 1)" = "$GAS_PREPROCESSOR_SHA256" ] || { echo 'gas-preprocessor checksum mismatch' >&2; exit 1; }
  mv "$gas.part" "$gas"
fi
mkdir -p "$src/libvlc/vlc/extras/tools/build/bin"
cp "$gas" "$src/libvlc/vlc/extras/tools/build/bin/gas-preprocessor.pl"
chmod +x "$src/libvlc/vlc/extras/tools/build/bin/gas-preprocessor.pl"
python3 "$root/tool/patch_vlckit.py" "$src"
# pkg-config may be supplied by Homebrew while autotools are built locally.
# Its pkg.m4 must remain visible to contrib's autoreconf calls.
pkg_config_bin="$(command -v pkg-config)"
aclocal_dir="$(dirname "$(dirname "$pkg_config_bin")")/share/aclocal"
export ACLOCAL_PATH="$aclocal_dir${ACLOCAL_PATH:+:$ACLOCAL_PATH}"
export MAKE_JOBS="${OPX_BUILD_JOBS:-$(sysctl -n hw.ncpu)}"
# Upstream uses -n so it cannot reset the pinned, patched VLC tree.
mkdir -p "$root/build"
log="$root/build/vlckit-$platform.log"
echo "Building $kit against package-ffmpeg (log: $log)"
if ! (cd "$src" && env -i PATH="$PATH" HOME="$HOME" USER="${USER:-}" \
  DEVELOPER_DIR="${DEVELOPER_DIR:-}" MAKE_JOBS="$MAKE_JOBS" \
  ACLOCAL_PATH="$ACLOCAL_PATH" OPX_FFMPEG_PACKAGE="$OPX_FFMPEG_PACKAGE" \
  bash buildMobileVLCKit.sh -n -v "${args[@]}") > "$log" 2>&1; then
  tail -80 "$log" >&2
  exit 1
fi
staging="$root/third_party/Frameworks-$platform.tmp"
rm -rf "$staging"
mkdir -p "$staging"
cp -R "$src/build/$kit.xcframework" "$staging/"
python3 "$root/tool/verify_vlckit.py" --rewrite "$staging/$kit.xcframework"
printf 'vlckit=%s\nvlc=%s\nplatform=%s\nffmpeg_package=%s\n' "$VLCKIT_REVISION" "$VLC_REVISION" "$platform" "$OPX_FFMPEG_PACKAGE" > "$staging/BUILDINFO"
cp "$src/COPYING" "$staging/COPYING.VLCKit"
cp "$src/libvlc/vlc/COPYING" "$staging/COPYING.VLC"
cp "$root/tool/vlc-sources.env" "$staging/SOURCES.env"
printf '%s\n' "$fingerprint" > "$staging/.fingerprint"
rm -rf "$out"
mv "$staging" "$out"
