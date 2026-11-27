#!/usr/bin/env python3
"""Reject embedded FFmpeg and require VLC modules to import the owner's ABI."""
from pathlib import Path
import os
import re
import shutil
import subprocess
import sys


def verify(target, prefix, ffmpeg):
    windows = target.startswith('windows-')
    android = target.startswith('android-')
    tool = os.environ.get('OPX_READELF', 'readelf')
    nm = os.environ.get('OPX_NM', 'nm')
    if android:
        ndk = Path(os.environ['ANDROID_NDK_HOME']) / 'toolchains/llvm/prebuilt'
        tc = next(ndk.glob('*/bin'))
        tool, nm = str(tc / 'llvm-readelf'), str(tc / 'llvm-nm')
    elif windows:
        tool = os.environ.get('OPX_OBJDUMP', shutil.which('objdump') or 'x86_64-w64-mingw32-objdump')
    libraries = sorted({p.resolve() for p in prefix.rglob('*') if p.is_file() and
                        (p.name.endswith('.dll') if windows else '.so' in p.name)})
    expected = {}
    required = set()
    if windows:
        for file in (ffmpeg / 'bin').glob('*.dll'):
            if re.match(r'(?:lib)?(?:avcodec|avformat|avutil|avfilter|swscale|swresample)[-\d.]', file.name):
                expected[file.name.lower()] = False
                if re.match(r'(?:lib)?(?:avcodec|avformat|avutil|swscale)[-\d.]', file.name):
                    required.add(file.name.lower())
    else:
        for name in ('avcodec', 'avformat', 'avutil', 'swscale', 'avfilter', 'swresample'):
            file = ffmpeg / 'lib' / f'lib{name}.so'
            if not file.exists():
                continue
            data = subprocess.check_output([tool, '-d', str(file)], text=True)
            soname = re.search(r'\(SONAME\).*?\[(.*?)\]', data)
            if not soname:
                raise RuntimeError(f'No shared FFmpeg SONAME: {file}')
            expected[soname[1]] = False
            if name in ('avcodec', 'avformat', 'avutil', 'swscale'):
                required.add(soname[1])
    if len(required) < 4:
        raise RuntimeError('Shared FFmpeg libraries are missing')
    for lib in libraries:
        data = subprocess.check_output([tool, '-p' if windows else '-d', str(lib)], text=True)
        imports = re.findall(r'DLL Name:\s*(\S+)', data) if windows else re.findall(r'\(NEEDED\).*?\[(.*?)\]', data)
        if windows and os.name == 'nt':
            packaged = {p.name.lower() for p in libraries} | set(expected)
            system = Path(os.environ['SYSTEMROOT']) / 'System32'
            for name in imports:
                if name.lower() not in packaged and not (system / name).is_file() and not name.lower().startswith(('api-ms-win-', 'ext-ms-win-')):
                    raise RuntimeError(f'{lib} imports an unbundled DLL: {name}')
        if android and 'libc++_shared.so' in imports and not (prefix / 'lib/libc++_shared.so').is_file():
            raise RuntimeError(f'{lib} requires the unbundled C++ runtime')
        for name in imports:
            key = name.lower() if windows else name
            if re.match(r'(?:lib)?(?:avcodec|avformat|avutil|swscale|swresample|avfilter)[.\-\d]', key):
                if key not in expected:
                    raise RuntimeError(f'{lib} imports a different FFmpeg ABI: {name}')
                if key in expected:
                    expected[key] = True
        if not windows and not android:
            env = dict(os.environ)
            env['LD_LIBRARY_PATH'] = f'{ffmpeg / "lib"}:{prefix / "bundle"}:{prefix / "lib"}:{env.get("LD_LIBRARY_PATH", "")}'
            closure = subprocess.run(['ldd', str(lib)], text=True, capture_output=True, env=env)
            if closure.returncode or 'not found' in closure.stdout:
                raise RuntimeError(f'Unresolved VLC dependencies: {lib}\n{closure.stdout}{closure.stderr}')
            for name, resolved in re.findall(r'^\s*(\S+) => (/\S+)', closure.stdout, re.M):
                if re.match(r'lib(?:avcodec|avformat|avutil|avfilter|swscale|swresample)\.', name):
                    if name not in expected or Path(resolved).resolve().parent != (ffmpeg / 'lib').resolve():
                        raise RuntimeError(f'{lib} transitively loads another FFmpeg: {name} => {resolved}')
        symbols = subprocess.run([nm, '--defined-only', str(lib)], text=True, capture_output=True)
        if symbols.returncode:
            raise RuntimeError(f'Cannot inspect symbols: {lib}\n{symbols.stderr}')
        definitions = re.findall(r'\b(_?(?:avcodec|avformat|avutil|av_frame|av_packet|sws|swr)_[a-z]\w*)$', symbols.stdout, re.M)
        if windows and definitions:
            # MinGW emits local jump thunks for DLL functions whose headers
            # have no dllimport annotation. These are imports, not static code.
            assembly = subprocess.check_output([tool, '-d', str(lib)], text=True)
            for name in definitions[:]:
                body = re.search(r'^0*[0-9a-f]+ <' + re.escape(name) + r'>:\n(.*?)(?=^[0-9a-f]+ <|\Z)', assembly, re.M | re.S)
                imported = re.search(r'^([0-9a-f]+)\s+I\s+__imp_' + re.escape(name.lstrip('_')) + r'$', symbols.stdout, re.M)
                jump = re.search(r'\bjmpq?\s+.*?#\s*(?:0x)?([0-9a-f]+)\s*<', body[1]) if body else None
                if imported and jump and int(imported[1], 16) == int(jump[1], 16):
                    # Only a single indirect jump and alignment padding may
                    # occupy the thunk; a real implementation must fail.
                    instructions = re.findall(r'^\s*[0-9a-f]+:\s+(?:[0-9a-f]{2}\s+)+(.+)$', body[1], re.M)
                    if instructions and all(re.match(r'(?:jmpq?\s|(?:cs )?nop|int3|xchg\s+%ax,%ax)', line) for line in instructions):
                        definitions.remove(name)
        if definitions:
            raise RuntimeError(f'{lib} embeds static FFmpeg: {definitions[:4]}')
        if re.match(r'(?:lib)?(?:avcodec|avformat|avutil|swscale|swresample|avfilter)[.\-\d]', lib.name):
            raise RuntimeError(f'VLC must not package its own FFmpeg: {lib}')
    missing = [k for k in required if not expected[k]]
    if missing:
        raise RuntimeError(f'VLC does not import the shared FFmpeg libraries: {missing}')
    print(f'Verified {target}: VLC imports package-ffmpeg ({len(libraries)} native binaries)')


if __name__ == '__main__':
    verify(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]))
