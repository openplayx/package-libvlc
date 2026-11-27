#!/usr/bin/env python3
"""Check real MinGW import thunks and embedded implementations without Windows."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from verify_libvlc import verify

TOOLS = ('clang', 'x86_64-w64-mingw32-ld', 'x86_64-w64-mingw32-objdump', 'x86_64-w64-mingw32-nm')


@unittest.skipUnless(all(shutil.which(t) for t in TOOLS), 'requires Clang and MinGW binutils')
class WindowsImportTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='opx-vlc-pe-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ffmpeg = self.root / 'ffmpeg'
        self.vlc = self.root / 'vlc'
        (self.ffmpeg / 'bin').mkdir(parents=True)
        self.vlc.mkdir()
        self.libs = ('avcodec', 'avformat', 'avutil', 'swscale')
        self.imports = []
        for name in self.libs:
            obj = self.compile(f'__declspec(dllexport) unsigned {name}_version(void) {{return 9;}}', name)
            library = self.root / (name + '.dll.a')
            self.link([obj], self.ffmpeg / 'bin' / (name + '-63.dll'), '--out-implib=' + str(library))
            self.imports.append(str(library))
        # FFmpeg headers intentionally lack dllimport: MinGW creates jump thunks.
        text = '\n'.join(f'unsigned {name}_version(void);' for name in self.libs)
        text += '\n__declspec(dllexport) unsigned vlc_test(void) { return '
        text += '+'.join(name + '_version()' for name in self.libs) + '; }'
        self.engine = self.compile(text, 'engine')
        self.environment = patch.dict(os.environ, OPX_OBJDUMP=TOOLS[2], OPX_NM=TOOLS[3])
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def compile(self, text, name):
        source, output = self.root / (name + '.c'), self.root / (name + '.o')
        source.write_text(text)
        subprocess.run([TOOLS[0], '-target', 'x86_64-w64-windows-gnu', '-c', str(source), '-o', str(output)], check=True)
        return str(output)

    def link(self, objects, output, *flags):
        subprocess.run([TOOLS[1], '--shared', '--entry=0', *objects, *flags, '-o', str(output)], check=True)

    def test_dll_import_thunks(self):
        self.link([self.engine, *self.imports], self.vlc / 'libvlc.dll')
        verify('windows-x86_64', self.vlc, self.ffmpeg)

    def test_static_implementation_with_dll_imports(self):
        embedded = self.compile('unsigned av_frame_alloc(void) {return 123;}', 'embedded')
        self.link([self.engine, embedded, *self.imports], self.vlc / 'libvlc.dll')
        with self.assertRaisesRegex(RuntimeError, 'static FFmpeg'):
            verify('windows-x86_64', self.vlc, self.ffmpeg)


if __name__ == '__main__':
    unittest.main()
