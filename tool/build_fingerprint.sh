#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
source "$root/tool/native_common.sh"
ffmpeg="${OPX_FFMPEG_PACKAGE:-$root/../ffmpeg-package}"
target="${1:?target required}"
files=(vlc-sources.env native_common.sh build_fingerprint.sh build_libvlc.sh
  patch_vlc_contrib.py verify_libvlc.py)
case "$target" in
  android-*) files+=(ensure_libvlc_android.sh prepare_libvlc_android.sh patch_libvlc_android.py) ;;
  *) files+=(stage_libvlc.py) ;;
esac
{
  echo "$target"
  for file in "${files[@]}"; do cat "$root/tool/$file"; done
  bash "$ffmpeg/tool/build_fingerprint.sh" "$target"
} | opx_sha | cut -d ' ' -f 1
# OPX_NATIVE_BUILD_HELPER: CI uses this key for third_party/libvlc/<target>.
