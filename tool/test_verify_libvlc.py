#!/usr/bin/env python3
"""Exercise the desktop/Android dependency verifier against real ELF libraries."""
from pathlib import Path
import subprocess
import sys
import shutil
import tempfile
import unittest

from verify_libvlc import verify


@unittest.skipUnless(sys.platform.startswith('linux') and all(shutil.which(t) for t in ('cc', 'readelf', 'nm', 'ldd')),
                     'requires Linux and ELF build/inspection tools')
class SharedFFmpegTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='opx-vlc-elf-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ffmpeg = self.root / 'ffmpeg'
        self.libs = ('avcodec', 'avformat', 'avutil', 'swscale')
        (self.ffmpeg / 'lib').mkdir(parents=True)
        for name in self.libs:
            self.library(self.ffmpeg / 'lib', name, 63)
        self.prefix = self.root / 'vlc'
        (self.prefix / 'lib').mkdir(parents=True)

    def library(self, folder, name, major):
        folder.mkdir(exist_ok=True)
        source = folder / f'{name}.c'
        source.write_text(f'unsigned {name}_version(void) {{ return 9; }}')
        output = folder / f'lib{name}.so.{major}'
        subprocess.run(['cc', '-shared', '-fPIC', str(source),
                        f'-Wl,-soname,{output.name}', '-o', str(output)], check=True)
        (folder / f'lib{name}.so').symlink_to(output.name)

    def engine(self, static=False, private=False, other_abi=False):
        source = self.root / 'engine.c'
        source.write_text('\n'.join(f'unsigned {name}_version(void);' for name in self.libs)
                          + '\nunsigned vlc_test(void) { return '
                          + ' + '.join(f'{name}_version()' for name in self.libs) + '; }\n'
                          + 'void avformat_OpenDemux(void) {}\n'
                          + ('unsigned avcodec_version(void) { return 1; }\n' if static else '')
                          + ('__attribute__((used)) static unsigned av_frame_alloc(void) { return 1; }\n' if private else ''))
        flags = []
        if other_abi:
            other = self.root / 'other'
            self.library(other, 'avcodec', 60)
            flags += [f'-L{other}']
        subprocess.run(['cc', '-shared', '-fPIC', str(source), *flags,
                        f'-L{self.ffmpeg / "lib"}', *(f'-l{name}' for name in self.libs),
                        '-o', str(self.prefix / 'lib/libvlc.so.5')], check=True)

    def test_shared_owner(self):
        self.engine()
        verify('linux-arm64', self.prefix, self.ffmpeg)

    def test_embedded_static_copy(self):
        self.engine(static=True)
        with self.assertRaisesRegex(RuntimeError, 'static FFmpeg'):
            verify('linux-arm64', self.prefix, self.ffmpeg)

    def test_embedded_private_copy(self):
        self.engine(private=True)
        with self.assertRaisesRegex(RuntimeError, 'static FFmpeg'):
            verify('linux-arm64', self.prefix, self.ffmpeg)

    def test_different_abi(self):
        self.engine(other_abi=True)
        with self.assertRaisesRegex(RuntimeError, 'different FFmpeg ABI'):
            verify('linux-arm64', self.prefix, self.ffmpeg)


if __name__ == '__main__':
    unittest.main()
