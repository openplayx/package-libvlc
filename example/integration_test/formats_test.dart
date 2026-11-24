// File format playback tests for LibVlcBackend: one test per sample of
// formats/manifest.json, prepared by tool/prepare_samples.py. Run them with
// tool/test_formats.sh, which passes the prepared list and report location:
//   --dart-define=OPX_SAMPLES=<resolved samples json>
//   --dart-define=OPX_REPORT=<report directory>
//
// Each sample is checked through the package's own backend, i.e. the same
// libVLC build and options as the app:
//   1. start: playing state and advancing position;
//   2. pipeline: VLC decoder statistics (decoded/displayed/lost pictures,
//      decoded/played/lost audio buffers) and the discovered tracks;
//   3. picture: the snapshot compared with the known SMPTE bars (corrupt or
//      green/grey frames, wrong colours);
//   4. sound: decoded audio is written to a WAV file (libVLC afile output),
//      and its level and frequency are compared with the 1 kHz tone (silence,
//      noise, wrong decoding);
//   5. duration, video size and a forward seek.
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:openplayx_playback/playback.dart';

const _samplesPath = String.fromEnvironment('OPX_SAMPLES');
const _reportPath = String.fromEnvironment('OPX_REPORT');

/// Diagnostics only: play through the system audio output instead of the
/// afile WAV output (the sound checks then fail for lack of a file).
const _systemAudio = bool.fromEnvironment('OPX_SYSTEM_AUDIO');

/// Mean absolute RGB difference (0..255) on the comparison grid above which a
/// snapshot no longer shows the expected picture. Lossy codecs and colour
/// matrix differences stay well below it; corruption does not.
const _maxFrameDiff = 24.0;

/// Share of lost pictures / audio buffers tolerated in the sampling window.
const _maxLossRatio = 0.1;

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  if (_samplesPath.isEmpty) {
    test('format samples are configured', () {
      fail('OPX_SAMPLES is not set; run tool/test_formats.sh');
    });
    return;
  }
  final samples = [
    for (final s
        in (jsonDecode(File(_samplesPath).readAsStringSync())
                as Map<String, dynamic>)['samples']
            as List)
      s as Map<String, dynamic>,
  ];
  final reportDir = Directory(_reportPath)..createSync(recursive: true);
  final results = <Map<String, dynamic>>[];
  tearDownAll(() {
    // One file per app launch; tool/format_report.py merges them.
    final name = File(_samplesPath).uri.pathSegments.last
        .replaceAll('samples', 'results');
    File('${reportDir.path}/$name').writeAsStringSync(
      const JsonEncoder.withIndent(' ').convert({'results': results}),
    );
  });

  for (final sample in samples) {
    testWidgets(sample['id'] as String, (tester) async {
      final check = _Check(sample);
      results.add(check.result);
      if (sample['status'] != 'ok') {
        check.fail('sample could not be prepared: ${sample['error']}');
      } else {
        await check.run(tester, reportDir);
      }
      check.result['result'] = check.failures.isEmpty ? 'passed' : 'failed';
      expect(check.failures, isEmpty, reason: check.failures.join('\n'));
    }, timeout: const Timeout(Duration(minutes: 2)));
  }
}

class _Check {
  _Check(this.sample)
    : result = {
        'id': sample['id'],
        'ext': sample['ext'],
        'linear': sample['linear'],
        'probe': sample['probe'],
        'note': sample['note'],
      };

  final Map<String, dynamic> sample;
  final Map<String, dynamic> result;
  final failures = <String>[];
  final metrics = <String, Object?>{};

  Map<String, dynamic> get expectations =>
      sample['expect'] as Map<String, dynamic>;
  Map<String, dynamic> get probe => sample['probe'] as Map<String, dynamic>;

  void fail(String message) {
    failures.add(message);
    result['failures'] = failures;
  }

  Future<void> run(WidgetTester tester, Directory reportDir) async {
    result['metrics'] = metrics;
    final id = sample['id'] as String;
    final wantVideo = expectations['video'] == true;
    final wantAudio = expectations['audio'] == true;
    final wav = File('${reportDir.path}/$id.wav');
    if (wav.existsSync()) wav.deleteSync();
    // Decoded audio goes to a WAV file instead of the speakers, so the test
    // can measure it and stays silent.
    final backend = LibVlcBackend(
      extraOptions: wantAudio && !_systemAudio
          ? [
              '--aout=afile',
              '--audiofile-file=${wav.path}',
              '--audiofile-format=s16',
              '--audiofile-wav',
            ]
          : const [],
    );
    var disposed = false;
    Future<void> release() async {
      if (disposed) return;
      disposed = true;
      await tester.pumpWidget(const SizedBox());
      backend.dispose();
      // libVLC finishes the WAV file when its audio output closes.
      await tester.pump(const Duration(milliseconds: 500));
    }

    addTearDown(release);

    Future<bool> waitFor(
      bool Function() condition, {
      Duration timeout = const Duration(seconds: 10),
    }) async {
      final watch = Stopwatch()..start();
      while (watch.elapsed < timeout) {
        await tester.pump(const Duration(milliseconds: 100));
        if (condition()) return true;
      }
      return false;
    }

    final width = (probe['width'] as int?) ?? 320;
    final height = (probe['height'] as int?) ?? 240;
    await tester.pumpWidget(
      ColoredBox(
        color: const Color(0xFF000000),
        child: Directionality(
          textDirection: TextDirection.ltr,
          child: Center(
            child: SizedBox(
              width: width.toDouble(),
              height: height.toDouble(),
              child: PlayerVideoView(backend: backend),
            ),
          ),
        ),
      ),
    );
    await tester.pump(const Duration(seconds: 1));

    // 1. Start.
    final opened = Stopwatch()..start();
    await backend.open(Uri.file(sample['path'] as String));
    final started = await waitFor(
      () =>
          backend.value.status == PlaybackStatus.error ||
          (backend.value.status == PlaybackStatus.playing &&
              backend.value.position > const Duration(milliseconds: 300) &&
              (!wantVideo || backend.value.videoSize != null)),
      timeout: const Duration(seconds: 15),
    );
    metrics['start_ms'] = opened.elapsedMilliseconds;
    if (!started || backend.value.status != PlaybackStatus.playing) {
      final ended = backend.value.status == PlaybackStatus.ended;
      fail(
        ended && backend.value.position == Duration.zero
            ? 'ended without reporting playback time (video '
                  '${backend.value.videoSize})'
            : 'did not start: ${backend.value.status}, position '
                  '${backend.value.position}, video ${backend.value.videoSize}',
      );
      await release();
      return;
    }

    // 3. Picture (early, while the media is certainly still playing).
    final frameRef = expectations['frame'] as String?;
    if (wantVideo) {
      try {
        final png = await backend.takeSnapshot();
        File('${reportDir.path}/$id.png').writeAsBytesSync(png);
        result['snapshot'] = '$id.png';
        if (frameRef != null) {
          final grid = (sample['grid'] as List).cast<int>();
          final diff = await _frameDiff(
            png,
            File(frameRef).readAsBytesSync(),
            grid[0],
            grid[1],
          );
          metrics['frame_diff'] = double.parse(diff.toStringAsFixed(1));
          if (diff > _maxFrameDiff) {
            fail(
              'picture differs from the source (mean diff '
              '${diff.toStringAsFixed(1)} > $_maxFrameDiff): corrupt or wrong colours',
            );
          }
        }
      } catch (e) {
        fail('snapshot failed: $e');
      }
    }

    // 2. Pipeline statistics over one second windows. A window with problems
    // is measured once more: start-up hiccups pass, sustained ones fail.
    for (var window = 1; window <= 2; window++) {
      final problems = await _statsWindow(
        tester,
        backend,
        wantVideo: wantVideo,
        wantAudio: wantAudio,
      );
      if (problems.isEmpty) break;
      if (window == 2) problems.forEach(fail);
    }
    try {
      final info = await backend.getMediaInfo();
      final types = [for (final t in info.tracks) t.type];
      metrics['tracks'] = [
        for (final t in info.tracks)
          {
            'type': t.type,
            'codec': t.codec,
            if (t.width != null) 'size': '${t.width}x${t.height}',
            if (t.channels != null) 'channels': t.channels,
            if (t.sampleRate != null) 'rate': t.sampleRate,
          },
      ];
      if (wantVideo && !types.contains('video')) fail('no video track found');
      if (wantAudio && !types.contains('audio')) fail('no audio track found');
    } catch (e) {
      fail('media info failed: $e');
    }

    // 5. Duration and size.
    final duration = backend.value.duration;
    metrics['duration_ms'] = duration.inMilliseconds;
    final wantDuration = expectations['duration_ms'] as int?;
    if (wantDuration != null &&
        (duration.inMilliseconds - wantDuration).abs() > 700) {
      fail(
        'duration ${duration.inMilliseconds} ms, expected ~$wantDuration ms',
      );
    }
    if (wantVideo) {
      final size = backend.value.videoSize;
      metrics['video_size'] = size == null
          ? null
          : '${size.width.round()}x${size.height.round()}';
      if (size == null ||
          size.width.round() != probe['width'] ||
          size.height.round() != probe['height']) {
        fail('video size $size, expected ${probe['width']}x${probe['height']}');
      }
    }

    // 5. Forward seek to the middle. Not closer to the end: with the afile
    // output libVLC reaches the end of short files early after a late seek.
    if (expectations['seek'] == true) {
      metrics['seekable'] = backend.value.canSeek;
      if (!backend.value.canSeek) {
        fail('not seekable');
      } else {
        final total = backend.value.duration;
        final target = total > Duration.zero
            ? total ~/ 2
            : const Duration(seconds: 4);
        final from = backend.value.position;
        await backend.seek(target);
        final landed = await waitFor(
          () =>
              backend.value.status == PlaybackStatus.playing &&
              (backend.value.position - target).abs() <
                  const Duration(milliseconds: 600),
          timeout: const Duration(seconds: 5),
        );
        final at = backend.value.position;
        final advances =
            landed &&
            await waitFor(
              () => backend.value.position > at,
              timeout: const Duration(seconds: 3),
            );
        metrics['seek_from_ms'] = from.inMilliseconds;
        metrics['seek_landed_ms'] = at.inMilliseconds;
        if (!landed || !advances) {
          fail(
            'seek to ${target.inMilliseconds} ms from ${from.inMilliseconds} ms: '
            '${backend.value.status} '
            'at ${backend.value.position}',
          );
        }
      }
    }

    // 4. Sound: measured after the audio output closed the file.
    await release();
    if (wantAudio) {
      final tone = expectations['tone_hz'] as int?;
      if (!wav.existsSync() || wav.lengthSync() <= 44) {
        fail('no decoded audio written (afile output)');
      } else {
        final level = _measure(wav.readAsBytesSync());
        metrics['audio_rms'] = double.parse(level.rms.toStringAsFixed(4));
        metrics['audio_hz'] = level.hz.round();
        metrics['audio_seconds'] = double.parse(
          level.seconds.toStringAsFixed(2),
        );
        if (tone != null) {
          if (level.rms < 0.02) {
            fail('silent: RMS ${level.rms.toStringAsFixed(4)}, tone expected');
          } else if ((level.hz - tone).abs() > tone * 0.05) {
            fail(
              'wrong sound: ${level.hz.round()} Hz, expected $tone Hz '
              '(noise or wrong decoding)',
            );
          }
        } else if (level.rms < 0.001) {
          fail('silent: RMS ${level.rms.toStringAsFixed(4)}');
        }
      }
      if (wav.existsSync()) wav.deleteSync();
    }
  }

  /// Decoder statistics over one second; returns the problems found.
  Future<List<String>> _statsWindow(
    WidgetTester tester,
    LibVlcBackend backend, {
    required bool wantVideo,
    required bool wantAudio,
  }) async {
    final before = await backend.getStats();
    await tester.pump(const Duration(seconds: 1));
    await tester.pump(const Duration(milliseconds: 100));
    final after = await backend.getStats();
    if (before == null || after == null) return ['no decoder statistics'];
    final decodedVideo = after.decodedVideo - before.decodedVideo;
    final displayed = after.displayedPictures - before.displayedPictures;
    final lostPictures = after.lostPictures - before.lostPictures;
    final decodedAudio = after.decodedAudio - before.decodedAudio;
    final played = after.playedAudioBuffers - before.playedAudioBuffers;
    final lostAudio = after.lostAudioBuffers - before.lostAudioBuffers;
    metrics.addAll({
      'video_decoded': decodedVideo,
      'video_displayed': displayed,
      'video_lost': lostPictures,
      'audio_decoded': decodedAudio,
      'audio_played': played,
      'audio_lost': lostAudio,
    });
    return [
      if (wantVideo && (decodedVideo <= 0 || displayed <= 0))
        'video stalled: decoded $decodedVideo, displayed $displayed in 1 s'
      else if (wantVideo &&
          lostPictures > _maxLossRatio * (displayed + lostPictures))
        'pictures dropped: $lostPictures lost, $displayed displayed in 1 s',
      if (wantAudio && (decodedAudio <= 0 || played <= 0))
        'audio stalled: decoded $decodedAudio, played $played in 1 s'
      else if (wantAudio && lostAudio > _maxLossRatio * (played + lostAudio))
        'audio buffers lost: $lostAudio lost, $played played in 1 s',
    ];
  }
}

/// Mean absolute RGB difference between a PNG snapshot and a raw RGB24
/// reference of [gw]×[gh] pixels, after box-averaging the snapshot to the grid.
Future<double> _frameDiff(
  Uint8List png,
  Uint8List reference,
  int gw,
  int gh,
) async {
  final codec = await ui.instantiateImageCodec(png);
  final image = (await codec.getNextFrame()).image;
  final w = image.width, h = image.height;
  final rgba = (await image.toByteData(format: ui.ImageByteFormat.rawRgba))!;
  image.dispose();
  var total = 0.0;
  for (var gy = 0; gy < gh; gy++) {
    final y0 = gy * h ~/ gh, y1 = math.max(y0 + 1, (gy + 1) * h ~/ gh);
    for (var gx = 0; gx < gw; gx++) {
      final x0 = gx * w ~/ gw, x1 = math.max(x0 + 1, (gx + 1) * w ~/ gw);
      final sum = [0, 0, 0];
      for (var y = y0; y < y1; y++) {
        for (var x = x0; x < x1; x++) {
          final o = (y * w + x) * 4;
          for (var c = 0; c < 3; c++) {
            sum[c] += rgba.getUint8(o + c);
          }
        }
      }
      final n = (y1 - y0) * (x1 - x0);
      for (var c = 0; c < 3; c++) {
        total += (sum[c] / n - reference[(gy * gw + gx) * 3 + c]).abs();
      }
    }
  }
  return total / (gw * gh * 3);
}

class _Level {
  const _Level(this.rms, this.hz, this.seconds);
  final double rms, hz, seconds;
}

/// RMS (0..1) and zero-crossing frequency of the first channel of a 16-bit
/// PCM WAV file. Chunk sizes are not trusted: libVLC may leave them unset.
_Level _measure(Uint8List bytes) {
  final data = ByteData.sublistView(bytes);
  var channels = 2, rate = 48000, offset = 12, start = -1;
  while (offset + 8 <= bytes.length) {
    final id = String.fromCharCodes(bytes.sublist(offset, offset + 4));
    final size = data.getUint32(offset + 4, Endian.little);
    if (id == 'fmt ') {
      channels = data.getUint16(offset + 10, Endian.little);
      rate = data.getUint32(offset + 12, Endian.little);
    }
    if (id == 'data') {
      start = offset + 8;
      break;
    }
    offset += 8 + size + (size & 1);
  }
  if (start < 0 || channels == 0 || rate == 0) return const _Level(0, 0, 0);
  final frames = (bytes.length - start) ~/ (2 * channels);
  // Skip the first 0.2 s (decoder priming, fades).
  final skip = math.min(frames, rate ~/ 5);
  var sum = 0.0;
  var crossings = 0;
  var previous = 0.0;
  for (var i = skip; i < frames; i++) {
    final v = data.getInt16(start + i * 2 * channels, Endian.little) / 32768;
    sum += v * v;
    if (i > skip && (previous < 0) != (v < 0)) crossings++;
    previous = v;
  }
  final n = frames - skip;
  if (n <= 0) return const _Level(0, 0, 0);
  final seconds = n / rate;
  return _Level(math.sqrt(sum / n), crossings / 2 / seconds, frames / rate);
}
