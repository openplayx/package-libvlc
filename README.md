# openplayx_playback (package-libvlc)

English | [简体中文](README.zh-CN.md)

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

The libVLC playback adapter of [OpenPlayX](https://github.com/openplayx/openplayx),
with playback integration tests maintained in the companion package-media repository.

```
OpenPlayX app → PlayerBackend (lib/playback.dart) → LibVlcBackend → vlc_player 2.1.2 (local fork) → libVLC / VLCKit
```

`vlc_player` uses the local `forks/vlc_player` with the 2.1.2 Dart API.
All native platforms build VLC against package-ffmpeg's shared FFmpeg, also
used by the processing bridge and libmpv. Apple uses VLCKit, Android builds
the official Java/JNI layer, and Linux/Windows build libVLC plus its plugins.
There is no fallback to precompiled AARs, downloaded VLC runtimes or system VLC.

## Apple native builds

Check out `ffmpeg-package` beside this package (or set `OPX_FFMPEG_PACKAGE`).
At `pod install`, `tool/ensure_vlckit_apple.sh macos|ios|tvos` builds FFmpeg and
VLCKit into `<platform>/Frameworks/*.xcframework`. Requires Xcode, Git, Python 3,
make, CMake, pkg-config and network access. VLC's tools recipe builds missing
tools into the local cache. The first build takes time; subsequent builds check
source, recipe and FFmpeg fingerprints.

`tool/vlc-sources.env` pins upstream sources. The official VLCKit VLC patch
series is applied in full. `tool/patch_vlckit.py` disables contrib's FFmpeg and
selects package-ffmpeg's matching target headers and shared libraries.
`tool/verify_vlckit.py` maps dylib references to the app's Av*/Sw* frameworks,
checks every slice's dependencies and rejects defined static FFmpeg symbols.
Logs: `build/vlckit-<platform>.log`; source cache: `third_party/`.

```sh
bash tool/ensure_vlckit_apple.sh macos
python3 tool/verify_vlckit.py macos/Frameworks/VLCKit.xcframework
```

Verified on 2026-11-26: macOS arm64/x86_64 framework builds and per-architecture
shared-library checks. The arm64 app's `integration_test/ffmpeg_bridge_test.dart`
forces libVLC software decoding, then probes and snapshots through the FFmpeg
processing bridge in the same process. Seven format regressions passed: H.264,
HEVC, VP9, AV1, MP3, Ogg/FLAC and Vorbis. On 2026-11-27 the iOS device arm64 and simulator arm64/x86_64 framework builds also passed shared-library checks. iOS and Android passed all seven format regressions; all three Android ABIs passed native checks. tvOS device/simulator arm64 frameworks passed, and the simulator decoded through avcodec then probed and snapshotted through the FFmpeg bridge in the same process. Linux arm64 passed native dependency checks and all seven format regressions in an image without system libVLC. Windows and Linux x86_64 still need native build/runtime validation on those hosts.

## Android, Linux and Windows builds

| Platform | Entry point | Runtime ownership |
| --- | --- | --- |
| Android (arm64-v8a, armeabi-v7a, x86_64) | `tool/ensure_libvlc_android.sh [abi...]`, called by the native plugin's Gradle configuration | This package builds Java/JNI and libvlc.so; package-ffmpeg packages libav*.so/libsw*.so once. Requires NDK 27+; API 29. |
| Linux (arm64, x86_64) | `tool/build_libvlc.sh linux-arm64\|linux-x86_64`, called by the plugin's CMake | Core libraries go in bundle/lib, VLC modules in bundle/lib/vlc/plugins. Desktop SDK dependencies remain system libraries; no system libVLC is linked. Requires CMake 3.19+ and the desktop GTK/XCB/PulseAudio/ALSA development SDKs (see the Linux Dockerfiles). |
| Windows (x86_64) | `tool/build_libvlc.sh windows-x86_64`, called by the plugin's CMake under MSYS2/MinGW-w64 | Source-built libvlc.dll/libvlccore.dll and plugins are bundled beside the app; the MSVC plugin links a COFF import library. FFmpeg DLLs are packaged by package-ffmpeg. |

`tool/vlc-sources.env` also pins the Android JNI/core revisions and its official
patch series. Native caches live in `third_party/libvlc/<target>` and are keyed
by `tool/build_fingerprint.sh`, including the FFmpeg recipe. Each entry point
runs `tool/verify_libvlc.py`: ELF/PE import checks must match the owner's ABI,
static/private FFmpeg definitions are rejected, and Linux's transitive loader
closure is checked for another FFmpeg. Windows CI builds and tests both engines.
Linux AppImage packaging preserves these plugins and rejects a second FFmpeg ABI.

```sh
ANDROID_NDK_HOME=/path/to/ndk bash tool/ensure_libvlc_android.sh arm64-v8a
bash tool/build_libvlc.sh linux-arm64  # on a matching Linux host
bash tool/build_libvlc.sh windows-x86_64  # in MSYS2
```

Desktop build entry points check contrib packages individually and retain passed
results. Compiler, source or global flag changes invalidate core objects; package
recipe changes rebuild affected dependencies and relink existing plugin objects.

Check an idle, already bootstrapped contrib tree independently, using the same
compiler environment as its original build:

```sh
CFLAGS='-O2 -g -std=gnu17' python3 -X utf8 tool/check_vlc_contrib.py --directory "$OPX_VLC_SOURCE_DIR/contrib/opx-windows-x86_64" --report build/dependency-checks --adopt-existing
CFLAGS='-O2 -g -std=gnu17' python3 -X utf8 tool/check_vlc_contrib.py --directory "$OPX_VLC_SOURCE_DIR/contrib/opx-windows-x86_64" --report build/sid-check --only sidplay2
```

Use `--adopt-existing` only on first use of an existing, previously verified
cache. Each package has its own log and result in `summary.json`; the first
failure stops the run. Successful packages remain cached when resuming.
`--rebuild sidplay2` or a changed package recipe invalidates that package and
its dependents, preserving unrelated packages. Compiler/configuration changes
require a separate source cache. System-provided libraries are not rebuilt by
this check; final DLL/ELF verification and playback tests remain separate.

## Usage

The app uses it as a sibling path dependency (CI checks it out as the
`package-libvlc` companion):

```yaml
dependencies:
  openplayx_playback:
    path: ../package-libvlc
```

```dart
final backend = LibVlcBackend();          // one native player per instance
PlayerVideoView(backend: backend);        // mount the video view first
await backend.open(Uri.file(path));       // autoplay
backend.value;                            // status, position, duration, video size …
await backend.getStats();                 // decoder counters (pictures, audio buffers)
backend.dispose();
```

`LibVlcBackend(extraOptions: [...])` appends libVLC instance options; the
format tests use it to write decoded audio to a file.

## File format playback tests

Playback integration tests, the sample manifest, preparation scripts and report
generator are maintained in [package-media](https://github.com/openplayx/package-media/blob/main/README.md#file-format-playback-tests).
Run the shared host with the libVLC engine:

```sh
cd ../package-media
bash tool/test_formats.sh --engine vlc
bash tool/test_formats.sh --engine vlc --pack --only 'pack-*'
```

Reports are written under package-media’s `build/formats/`, unless
`OPX_REPORT_DIR` is set.

See [sample preparation and checks](https://github.com/openplayx/package-media/blob/main/formats/README.md).
Adapter unit tests remain here: `flutter test`.

## Development

```sh
flutter analyze                           # package
(cd example && flutter analyze)           # example host app
```

## License

MIT, see [LICENSE](LICENSE). VLC and VLCKit retain their upstream licenses. The native artifacts on all platforms link package-ffmpeg's GPL build and are recorded as a GPL combination; Apple native license texts are staged in Frameworks/.
