import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:openplayx_playback/playback.dart';

void main() {
  List<String> options(String uri, [TargetPlatform p = TargetPlatform.iOS]) =>
      LibVlcBackend.mediaOptionsFor(Uri.parse(uri), platform: p);

  test('MP3 uses the avformat demuxer on every platform and scheme', () {
    for (final p in TargetPlatform.values) {
      expect(options('file:///music/a.MP3', p), [':demux=avformat']);
      expect(options('https://host/a.mp3?token=1', p), [':demux=avformat']);
      expect(options('smb://host/share/a.mp3', p), [':demux=avformat']);
    }
  });

  test('network MP4 uses avformat on macOS only', () {
    expect(options('https://host/a.mp4', TargetPlatform.macOS), [
      ':demux=avformat',
    ]);
    expect(options('https://host/a.mp4', TargetPlatform.iOS), isEmpty);
    expect(options('file:///a.mp4', TargetPlatform.macOS), isEmpty);
  });

  test('other media keep libVLC defaults', () {
    expect(options('file:///a.mkv'), isEmpty);
    expect(options('file:///a.flac'), isEmpty);
    expect(options('file:///mp3/a.m4a'), isEmpty);
  });
}
