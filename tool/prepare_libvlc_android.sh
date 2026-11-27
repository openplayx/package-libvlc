#!/usr/bin/env bash
# Fetch pinned Java/JNI sources before Gradle enumerates Java and resources.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
source "$root/tool/vlc-sources.env"
source "$root/tool/native_common.sh"
opx_lock "$root/third_party/.lock-android-sources"
jni="$root/third_party/libvlcjni"
opx_checkout https://code.videolan.org/videolan/libvlcjni.git "$LIBVLCJNI_REVISION" "$jni"
opx_checkout https://github.com/videolan/vlc.git "$ANDROID_VLC_REVISION" "$jni/vlc"
stamp="$jni/vlc/.opx-jni-patches"
if [ "$(cat "$stamp" 2>/dev/null || true)" != "$LIBVLCJNI_REVISION:$ANDROID_VLC_REVISION" ]; then
  git -C "$jni/vlc" reset --hard "$ANDROID_VLC_REVISION"
  git -C "$jni/vlc" clean -fd
  for patch in "$jni"/libvlc/patches/*.patch; do git -C "$jni/vlc" apply --whitespace=nowarn "$patch"; done
  printf '%s\n' "$LIBVLCJNI_REVISION:$ANDROID_VLC_REVISION" > "$stamp"
fi
python3 "$root/tool/patch_vlc_contrib.py" "$jni/vlc"
python3 "$root/tool/patch_libvlc_android.py" "$jni"
