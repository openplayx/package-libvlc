# openplayx_playback (package-libvlc)

English | [简体中文](README.zh-CN.md)

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

The libVLC playback adapter of [OpenPlayX](https://github.com/openplayx/openplayx),
with playback integration tests maintained in the companion package-media repository.

```
OpenPlayX app → PlayerBackend (lib/playback.dart) → LibVlcBackend → vlc_player 2.1.2 → libVLC (VLCKit 3.7.3 on Apple)
```

`vlc_player` is pinned exactly: a format test result describes one libVLC
build, so the app and these tests must resolve the same version.

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

MIT, see [LICENSE](LICENSE). libVLC and VLCKit keep their own (LGPL) terms.
