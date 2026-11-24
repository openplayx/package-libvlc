# openplayx_playback example

Host app for the file format playback tests in `integration_test/`; run them
with `../tool/test_formats.sh` (see the package README). The macOS app sandbox
is off so libVLC can open samples from the cache directory and write the
decoded audio file.

`flutter run -d macos --dart-define=OPX_MEDIA=/path/to/file` plays one file.
