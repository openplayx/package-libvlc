# The native VLC engine shares package-ffmpeg's FFmpeg frameworks.
root = File.expand_path('..', File.realpath(__dir__))
system('bash', File.join(root, 'tool', 'ensure_vlckit_apple.sh'), 'macos') ||
  raise('Building VLCKit failed; see package-libvlc/build/vlckit-macos.log')

Pod::Spec.new do |s|
  s.name = 'openplayx_playback'
  s.version = '0.1.0'
  s.summary = 'OpenPlayX libVLC built against package-ffmpeg'
  s.homepage = 'https://github.com/openplayx/package-libvlc'
  s.license = { :type => 'GPL-2.0-or-later' }
  s.author = 'OpenPlayX'
  s.source = { :path => '.' }
  s.platform = :osx, '12.0'
  s.dependency 'FlutterMacOS'
  s.dependency 'openplayx_ffmpeg'
  s.vendored_frameworks = 'Frameworks/VLCKit.xcframework'
end
