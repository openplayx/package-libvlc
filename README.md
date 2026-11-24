# openplayx_playback (package-libvlc)

English | [简体中文](README.zh-CN.md)

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

The libVLC playback adapter of [OpenPlayX](https://github.com/openplayx/openplayx),
plus the file format playback tests that decide which formats OpenPlayX can
claim to play.

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

The tests do **not** run by default (they are not under `test/`, and the app's
CI does not run them). Run them when this package changes: the adapter, the
`vlc_player` version, the libVLC/VLCKit build or `formats/`.

```sh
brew install ffmpeg                       # sample generation and ffprobe
tool/test_formats.sh                      # all samples, macOS
tool/test_formats.sh --only 'mp4-*,mp3'   # ids or globs
```

The run writes `build/formats/<timestamp>/report.md` (plus `results.json`,
snapshots and the Flutter log) and exits non-zero when a sample fails.

### What a sample is

[`formats/manifest.json`](formats/manifest.json) lists the samples with the
Linear issues they verify. `tool/prepare_samples.py` prepares them into
`~/.cache/openplayx-libvlc-samples` (`OPX_SAMPLE_CACHE`), never into the
repository:

- `generate`: encoded locally with ffmpeg from SMPTE colour bars (320×240,
  25 fps) and a 1 kHz stereo tone, 6 s. No licensing questions, and the test
  knows exactly what the picture and the sound must be.
- `url` + `sha256`: downloaded (retried, size-limited) and verified.
- `playlist`: a pls/m3u/asx/cue file pointing at another sample.

Every prepared file is checked with ffprobe, so the real container and codecs
are recorded instead of trusting the extension.

### What is checked

Each sample plays through `LibVlcBackend` in the `example/` host app, so the
result covers the same libVLC build and options as OpenPlayX:

| Check | Catches |
|---|---|
| playing state and advancing time | does not open, does not start |
| decoder statistics over 1 s (re-measured once) | black screen, stalled or dropping video, stalled or lost audio |
| tracks found by libVLC | missing video or audio track |
| snapshot vs. the SMPTE bars (mean RGB difference on a 32×24 grid, limit 24) | corrupt pictures, green/grey frames, wrong colours |
| decoded audio written with libVLC's `afile` output: RMS and frequency vs. the 1 kHz tone | silence, noise, wrong decoding |
| duration and video size | wrong timing or dimensions |
| seek to the middle | seek failures, playback ending after a seek |

Limits: the bars are a still picture, so damage only shows when it hits a
keyframe (a corrupted keyframe scores ~87, clean samples ~9); the snapshot is
the decoded picture, not what Flutter renders (HDR
tone mapping and on-screen colour need their own tests); `afile` measures the
decoded audio, not the device output (passthrough needs a receiver).

### Known issues

- A player can disturb later players in the same process: after about 30 s of
  playback by earlier (disposed) players, or one raw `.m2v` stream, later
  videos drop most pictures. The run therefore restarts the host app every 6
  samples (`OPX_BATCH`) and reruns each failed sample alone; the report marks
  samples that passed only alone. Under investigation; it may affect the app
  when many videos play in one session.

## Development

```sh
flutter analyze                           # package
(cd example && flutter analyze)           # host app and tests
```

## License

MIT, see [LICENSE](LICENSE). libVLC and VLCKit keep their own (LGPL) terms.
