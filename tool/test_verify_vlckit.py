#!/usr/bin/env python3
"""Exercise the verifier against real Mach-O binaries (macOS/Xcode required)."""
from pathlib import Path
import plistlib
import subprocess
import sys
import shutil
import tempfile
import unittest

from verify_vlckit import verify


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('xcrun'), 'requires macOS and Xcode tools')
class FrameworkVerificationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='opx-vlckit-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.libs = ('avcodec', 'avformat', 'avutil', 'swscale')
        for lib in self.libs:
            source = self.root / f'{lib}.c'
            source.write_text(f'unsigned {lib}_version(void) {{ return 9; }}\n')
            subprocess.run(['xcrun', 'clang', '-dynamiclib', str(source),
                            '-install_name', f'@rpath/lib{lib}.63.dylib',
                            '-o', str(self.root / f'lib{lib}.dylib')], check=True)

    def framework(self, static_ffmpeg=False, private_ffmpeg=False):
        xc = self.root / 'Test.xcframework'
        fw = xc / 'macos-arm64' / 'Test.framework'
        (fw / 'Versions/A/Resources').mkdir(parents=True)
        (fw / 'Versions/Current').symlink_to('A')
        (fw / 'Test').symlink_to('Versions/Current/Test')
        (fw / 'Resources').symlink_to('Versions/Current/Resources')
        info = dict(CFBundleExecutable='Test', CFBundleIdentifier='org.openplayx.test',
                    CFBundleName='Test', CFBundlePackageType='FMWK', CFBundleVersion='1')
        (fw / 'Resources/Info.plist').write_bytes(plistlib.dumps(info))
        source = self.root / 'test.c'
        source.write_text('\n'.join(f'unsigned {lib}_version(void);' for lib in self.libs)
                          + '\nunsigned test(void) { return '
                          + ' + '.join(f'{lib}_version()' for lib in self.libs) + '; }\n'
                          + 'void avformat_OpenDemux(void) {}\n'
                          + ('unsigned avcodec_version(void) { return 1; }\n' if static_ffmpeg else '')
                          + ('__attribute__((used)) static unsigned av_frame_alloc(void) { return 1; }\n' if private_ffmpeg else ''))
        subprocess.run(['xcrun', 'clang', '-dynamiclib', str(source),
                        '-Wl,-headerpad_max_install_names', f'-L{self.root}',
                        *(f'-l{lib}' for lib in self.libs),
                        '-o', str(fw / 'Versions/A/Test')], check=True)
        return xc

    def test_rejects_raw_dylib_references(self):
        with self.assertRaisesRegex(RuntimeError, 'does not link shared'):
            verify(self.framework())

    def test_rewrites_and_verifies_framework_dependencies(self):
        xc = self.framework()
        verify(xc, rewrite=True)
        verify(xc)

    def test_rejects_embedded_static_ffmpeg(self):
        with self.assertRaisesRegex(RuntimeError, 'embeds static FFmpeg'):
            verify(self.framework(static_ffmpeg=True), rewrite=True)

    def test_rejects_private_static_ffmpeg(self):
        with self.assertRaisesRegex(RuntimeError, 'embeds static FFmpeg'):
            verify(self.framework(private_ffmpeg=True), rewrite=True)


if __name__ == '__main__':
    unittest.main()
