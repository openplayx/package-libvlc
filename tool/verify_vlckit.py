#!/usr/bin/env python3
"""Rewrite/verify all VLCKit slices use the app's shared FFmpeg frameworks."""
import argparse
from pathlib import Path
import re
import subprocess


def run(*args):
    return subprocess.check_output(args, text=True)


def verify(path: Path, rewrite=False):
    frameworks = sorted(path.glob('*/*.framework'))
    if not frameworks:
        raise RuntimeError(f'No frameworks in {path}')
    for framework in frameworks:
        binary = framework / framework.stem
        sub = 'Versions/A/' if (framework / 'Versions/A').is_dir() else ''
        refs = set(re.findall(r'^\s*(\S+) \(compatibility version', run('otool', '-L', str(binary)), re.M))
        if rewrite:
            args = ['install_name_tool', '-id', f'@rpath/{framework.name}/{sub}{framework.stem}']
            for ref in sorted(refs):
                match = re.search(r'(?:^|/)lib(av\w+|swscale|swresample)(?:\.\d+)*\.dylib$', ref)
                if match:
                    lib = match[1]
                    name = ('Av' + lib[2:]) if lib.startswith('av') else ('Sw' + lib[2:])
                    args += ['-change', ref, f'@rpath/{name}.framework/{sub}{name}']
            subprocess.run(args + [str(binary)], check=True)
            subprocess.run(['codesign', '--force', '--sign', '-', str(framework)], check=True)
        for arch in run('lipo', '-archs', str(binary)).split():
            refs = '\n'.join(re.findall(r'^\s*(\S+) \(compatibility version',
                                        run('otool', '-arch', arch, '-L', str(binary)), re.M))
            for name in ('Avcodec', 'Avformat', 'Avutil', 'Swscale'):
                if f'@rpath/{name}.framework/{sub}{name}' not in refs:
                    raise RuntimeError(f'{binary} ({arch}) does not link shared {name}')
            if re.search(r'(?:/lib(?:av\w+|swscale|swresample).*\.dylib|third_party/)', refs):
                raise RuntimeError(f'{binary} ({arch}) has unbundled library references:\n{refs}')
            # Include private/local symbols: hiding FFmpeg is still a second copy.
            symbols = run('nm', '-arch', arch, '-U', str(binary))
            if re.search(r'\b_(?:avcodec|avformat|avutil|av_frame|av_packet|sws|swr)_[a-z]\w*$', symbols, re.M):
                raise RuntimeError(f'{binary} ({arch}) embeds static FFmpeg symbols')
            print(f'Verified shared FFmpeg ({arch}): {binary}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rewrite', action='store_true')
    parser.add_argument('framework', type=Path)
    args = parser.parse_args()
    verify(args.framework, args.rewrite)
