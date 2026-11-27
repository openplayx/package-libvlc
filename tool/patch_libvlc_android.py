#!/usr/bin/env python3
"""Adapt official Android JNI build to shared FFmpeg and the project's NDK."""
from pathlib import Path
import subprocess
import sys

root = Path(sys.argv[1])
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
