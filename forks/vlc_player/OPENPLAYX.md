# OpenPlayX fork of vlc_player 2.1.2

Upstream: https://github.com/lingjhf/vlc_player (pub.dev release 2.1.2).
The upstream MIT license and third-party notices are retained here.

The Dart API is unchanged. The macOS and
iOS podspecs depend on `openplayx_playback`, which builds VLCKit from the pinned
sources in `../../tool/vlc-sources.env` and links package-ffmpeg's shared FFmpeg.
All native dependencies are OpenPlayX source builds. The original precompiled
VLCKit pods, Android libvlc-all AAR and Windows runtime download are removed;
Linux no longer resolves system libVLC. Android depends on the native
openplayx_playback Gradle project. Desktop CMake calls the pinned VLC build and
preserves its module directory. FFmpeg binaries remain owned by package-ffmpeg.

Android snapshots read the actual video TextureView instead of the Activity
window, which can exclude Flutter virtual-display content. Linux supplies a
valid black texture before the first decoded frame. The shared desktop RGBA
callback requests the visible track dimensions instead of decoder padding.
