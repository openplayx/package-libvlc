import 'package:flutter/widgets.dart';
import 'package:openplayx_playback/playback.dart';

/// Minimal host: plays the file given with `--dart-define=OPX_MEDIA=<path>`,
/// with extra libVLC options from `--dart-define=OPX_VLC_OPTIONS=...` (space
/// separated, e.g. `--verbose=2` to log to stderr). The format tests in
/// integration_test/ mount their own player views.
void main() => runApp(const ExampleApp());

class ExampleApp extends StatefulWidget {
  const ExampleApp({super.key});

  @override
  State<ExampleApp> createState() => _ExampleAppState();
}

class _ExampleAppState extends State<ExampleApp> {
  final _backend = LibVlcBackend(
    extraOptions: [
      for (final o in const String.fromEnvironment(
        'OPX_VLC_OPTIONS',
      ).split(' '))
        if (o.isNotEmpty) o,
    ],
  );

  @override
  void initState() {
    super.initState();
    const media = String.fromEnvironment('OPX_MEDIA');
    if (media.isNotEmpty) {
      Future.delayed(
        const Duration(seconds: 1),
        () => _backend.open(Uri.file(media)),
      );
    }
  }

  @override
  void dispose() {
    _backend.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => ColoredBox(
    color: const Color(0xFF000000),
    child: Directionality(
      textDirection: TextDirection.ltr,
      child: PlayerVideoView(backend: _backend),
    ),
  );
}
