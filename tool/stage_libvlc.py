#!/usr/bin/env python3
"""Stage relocatable desktop runtime libraries; FFmpeg remains its owner's asset."""
from pathlib import Path
import shutil
import subprocess
import sys

target, directory, source = sys.argv[1:]
prefix = Path(directory)
bundle = prefix / 'bundle'
shutil.rmtree(bundle, ignore_errors=True)
bundle.mkdir()
if target.startswith('linux-'):
    # VLC's shared module helpers (for example PulseAudio) are installed
    # beneath lib/vlc, but must sit beside the core in the Flutter bundle.
    runtime = list((prefix / 'lib').glob('libvlc*.so*')) + list((prefix / 'lib/vlc').glob('*.so*'))
    for lib in runtime:
        if lib.is_symlink():
            continue
        rpath = '$ORIGIN:$ORIGIN/..' if lib.parent.name == 'vlc' else '$ORIGIN'
        subprocess.run(['patchelf', '--set-rpath', rpath, str(lib)], check=True)
        soname = subprocess.check_output(['patchelf', '--print-soname', str(lib)], text=True).strip()
        out = bundle / soname
        shutil.copy2(lib, out)
        subprocess.run(['patchelf', '--set-rpath', '$ORIGIN', str(out)], check=True)
    for plugin in (prefix / 'lib/vlc/plugins').rglob('*.so'):
        subprocess.run(['patchelf', '--set-rpath', '$ORIGIN:$ORIGIN/../../..', str(plugin)], check=True)
else:
    for lib in list((prefix / 'bin').glob('*.dll')) + list((prefix / 'lib/vlc').glob('*.dll')):
        shutil.copy2(lib, bundle / lib.name)
    header = prefix / 'include/vlc/libvlc_media.h'
    header.write_text(header.read_text().replace('typedef SSIZE_T ssize_t;',
                      '#if _MSC_VER < 1900\ntypedef SSIZE_T ssize_t;\n#endif'))
    # COFF import library consumed by the MSVC-built Flutter plugin.
    exports = 'LIBRARY libvlc.dll\nEXPORTS\n' + (Path(source) / 'lib/libvlc.sym').read_text()
    definition = prefix / 'lib/libvlc.def'
    definition.write_text(exports)
    subprocess.run(['dlltool', '-m', 'i386:x86-64', '-D', 'libvlc.dll', '-d', str(definition),
                    '-l', str(prefix / 'lib/libvlc.lib')], check=True)
