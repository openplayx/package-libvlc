#!/usr/bin/env python3
"""Adapt official Android JNI build to shared FFmpeg and the project's NDK."""
import base64
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request

# Official AOSP compatibility sources. Kept outside the installed NDK; all
# downloads are immutable and checked before entering a native build.
CPU_FEATURES_REVISION = 'c4bdd155116a9b42767534b35e93f83a91e4a06f'
CPU_FEATURES_SHA256 = {
    'cpu-features.c': '1b8a88eb7d3a5437d17e12475539398d3e1c5eef13d85941679841254af0a8f5',
    'cpu-features.h': 'f4989fabece7ea538e3c1272dca47f8a9a4423a87c79a1344a2611e884cb7319',
}


def ensure_cpu_features(directory, opener=None):
    opener = opener or urllib.request.urlopen
    directory.mkdir(parents=True, exist_ok=True)
    for name, expected in CPU_FEATURES_SHA256.items():
        dest = directory / name
        if dest.is_file() and hashlib.sha256(dest.read_bytes()).hexdigest() == expected:
            continue
        url = (f'https://android.googlesource.com/platform/ndk/+/{CPU_FEATURES_REVISION}/'
               f'sources/android/cpufeatures/{name}?format=TEXT')
        with opener(url, timeout=30) as response:
            data = base64.b64decode(b''.join(response.read().split()), validate=True)
        if hashlib.sha256(data).hexdigest() != expected:
            raise RuntimeError(f'AOSP cpu-features checksum mismatch: {name}')
        with tempfile.NamedTemporaryFile(dir=directory, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
        os.replace(temporary, dest)
    header = (directory / 'cpu-features.h').read_text()
    notice = header[:header.index('*/') + 2] + '\n'
    (directory / 'NOTICE').write_text(notice)


def patch_cpu_features_rule(rule, directory):
    text = rule.read_text()
    text = text.replace('"${ANDROID_NDK}"/sources/android/cpufeatures/', '"$(OPX_CPUFEATURES_DIR)"/')
    text = text.replace('"${ANDROID_NDK}/sources/android/cpufeatures/', '"$(OPX_CPUFEATURES_DIR)/')
    if 'sources/android/cpufeatures' in text:
        raise RuntimeError('unrecognized NDK cpu-features reference in libvpx recipe')
    if '$(OPX_CPUFEATURES_DIR)' not in text:
        raise RuntimeError('libvpx recipe no longer contains its expected cpu-features inputs')
    assignment = f'OPX_CPUFEATURES_DIR := {directory.as_posix()}'
    if re.search(r'^OPX_CPUFEATURES_DIR :=.*$', text, re.M):
        text = re.sub(r'^OPX_CPUFEATURES_DIR :=.*$', lambda _: assignment, text, flags=re.M)
    else:
        text = assignment + '\n' + text
    rule.write_text(text)


def patch(root):
    features = root.parent / 'android-cpufeatures'
    ensure_cpu_features(features)
    patch_cpu_features_rule(root / 'vlc/contrib/src/vpx/rules.mak', features)
    notices = root / 'libvlc/assets/licenses'
    notices.mkdir(parents=True, exist_ok=True)
    shutil.copy2(features / 'NOTICE', notices / 'android-cpufeatures.txt')
    script = subprocess.check_output(['git', 'show', 'HEAD:buildsystem/compile-libvlc.sh'], cwd=root, text=True)
    start = script.index('if [ "${HAVE_64}" = 1 ]; then')
    end = script.index('############\n# VLC PATH', start)
    script = script[:start] + '''# All supported ABIs use the same modern NDK and app minimum API.
    if [ "$REL" -lt 27 ]; then
        echo "NDK 27+ is required for all OpenPlayX ABIs" >&2
        exit 1
    fi
    ANDROID_API=29

    ''' + script[end:]
    script = script.replace('"$VLC_CONTRIB/lib/pkgconfig/"',
                            '"$VLC_CONTRIB/lib/pkgconfig/:$OPX_FFMPEG_PKGCONFIG"')
    script = script.replace('    --enable-ad-clauses \\\n', '    --disable-ffmpeg --disable-postproc --disable-x264 --disable-x262 \\\n')
    script = script.replace('$(ls *.pc  | sed', '$(ls *.pc | grep -v \"^protobuf.pc$\" | sed')
    script = script.replace('echo -e "ndk-build vlc"',
                            'VLC_CONTRIB_LDFLAGS="$VLC_CONTRIB_LDFLAGS -L$OPX_FFMPEG_PREFIX/lib -lavcodec -lavformat -lavutil -lswscale -lswresample -lavfilter"\n\necho -e "ndk-build vlc"')
    script = script.replace('PKG_CONFIG_LIBDIR=$VLC_SRC_DIR/contrib/$TARGET_TUPLE/lib/pkgconfig',
                            'PKG_CONFIG_LIBDIR=$VLC_SRC_DIR/contrib/$TARGET_TUPLE/lib/pkgconfig:$OPX_FFMPEG_PKGCONFIG')
    script = script.replace('PKG_CONFIG_PATH=$VLC_SRC_DIR/contrib/$TARGET_TUPLE/lib/pkgconfig',
                            'PKG_CONFIG_PATH=$VLC_SRC_DIR/contrib/$TARGET_TUPLE/lib/pkgconfig:$OPX_FFMPEG_PKGCONFIG')
    script = script.replace('../bootstrap --host=${TARGET_TUPLE}',
                            '../bootstrap --build="$(sh \"$VLC_SRC_DIR/autotools/config.guess\")" --host=${TARGET_TUPLE}')
    script = script.replace('--build=x86_64-unknown-linux', '--build=$(sh "$VLC_SRC_DIR/autotools/config.guess")')
    anchor = '# disable forced -lc++ in contribs'
    script = script.replace(anchor, '''# Remove stale archives from any previous non-shared FFmpeg build.
    rm -f "$VLC_CONTRIB"/lib/libav*.a "$VLC_CONTRIB"/lib/libsw*.a
    rm -f "$VLC_CONTRIB"/lib/pkgconfig/libav*.pc "$VLC_CONTRIB"/lib/pkgconfig/libsw*.pc
    rm -rf "$VLC_CONTRIB"/include/libav* "$VLC_CONTRIB"/include/libsw*

    ''' + anchor)
    path = root / 'buildsystem/compile-libvlc.sh'
    if path.read_text() != script:
        path.write_text(script)


if __name__ == '__main__':
    patch(Path(sys.argv[1]))
