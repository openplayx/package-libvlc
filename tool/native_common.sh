#!/usr/bin/env bash
# Internal helpers for pinned source caches, shared FFmpeg, and build locks.
opx_checkout() {
  local url="$1" revision="$2" dir="$3"
  if [ ! -d "$dir/.git" ]; then
    git init -q "$dir"
    git -C "$dir" remote add origin "$url"
  fi
  if ! git -C "$dir" cat-file -e "$revision^{commit}" 2>/dev/null; then
    git -C "$dir" fetch -q --depth 1 origin "$revision"
  fi
  if [ "$(git -C "$dir" rev-parse HEAD 2>/dev/null || true)" != "$revision" ]; then
    git -C "$dir" checkout -q --force --detach "$revision"
    git -C "$dir" clean -fdx
  fi
}
opx_sha() { if command -v sha256sum >/dev/null; then sha256sum; else shasum -a 256; fi; }
opx_lock() {
  local lock="$1" holder
  mkdir -p "$(dirname "$lock")"
  until mkdir "$lock" 2>/dev/null; do
    holder="$(cat "$lock/pid" 2>/dev/null || true)"
    if [ -n "$holder" ] && ! kill -0 "$holder" 2>/dev/null; then rm -rf "$lock"; continue; fi
    sleep 2
  done
  echo $$ > "$lock/pid"
  OPX_LOCK_PATH="$lock"
  trap 'rm -rf "$OPX_LOCK_PATH"' EXIT
}
opx_ensure_ffmpeg() {
  local target="$1" ff="$OPX_FFMPEG_PACKAGE/third_party/ffmpeg/$1"
  if [ ! -f "$ff/BUILD_FINGERPRINT" ] ||
     [ "$(cat "$ff/BUILD_FINGERPRINT")" != "$(bash "$OPX_FFMPEG_PACKAGE/tool/build_fingerprint.sh" "$target")" ]; then
    bash "$OPX_FFMPEG_PACKAGE/tool/build_ffmpeg.sh" "$target"
  fi
  export OPX_FFMPEG_PKGCONFIG="$ff/lib/pkgconfig"
}
# OPX_NATIVE_BUILD_HELPER: sourced by the libVLC native build entry points.
