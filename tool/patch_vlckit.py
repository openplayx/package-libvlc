#!/usr/bin/env python3
"""Adapt the pinned upstream Apple recipe to package-ffmpeg shared libraries.

Always read the pristine recipe from git, so rerunning this is idempotent.
Unexpected upstream changes fail instead of silently building a second FFmpeg.
"""
from pathlib import Path
import subprocess
import sys


def write_if_changed(path: Path, text: str):
    if not path.exists() or path.read_text() != text:
        path.write_text(text)


def patch(root: Path):
    script = subprocess.check_output(
        ['git', 'show', 'HEAD:buildMobileVLCKit.sh'], cwd=root, text=True)

    def replace(old, new):
        nonlocal script
        if script.count(old) != 1:
            raise RuntimeError(f'Expected one upstream anchor: {old!r}')
        script = script.replace(old, new)

    # Keep host build tools available. Upstream builds missing autotools locally.
    replace('${VLC_PATH}:/usr/bin', '${VLC_PATH}:${PATH}:/usr/bin')
    replace('             MACOS=yes\n             IOS=no',
            '             MACOS=yes\n             BUILD_SIMULATOR=no\n             IOS=no')
    replace('ROOT_DIR=`pwd`', 'ROOT_DIR=`pwd`\nTHIS_SCRIPT_PATH="$ROOT_DIR/buildMobileVLCKit.sh"')
    replace('SDK_MIN=9.0', 'SDK_MIN=15.0')
    replace('SDK_MIN=10.2', 'SDK_MIN=15.0')
    replace('SDK_MIN=10.9', 'SDK_MIN=12.0')
    replace('    make .buildgas', '    # gas-preprocessor is supplied by the pinned OpenPlayX helper.')
    # This repository ships only the arm64 tvOS simulator slice, as FFmpeg does.
    replace('architectures="x86_64 arm64"\n            else',
            'architectures="arm64"\n            else')
    replace('            if [ "$TVOS" = "yes" ]; then\n                if [ "$PLATFORM" = "iphonesimulator" ]; then\n                    buildLibVLC "x86_64" "Simulator"\n'
            '                    buildLibVLC "aarch64" "Simulator"',
            '            if [ "$TVOS" = "yes" ]; then\n                if [ "$PLATFORM" = "iphonesimulator" ]; then\n                    buildLibVLC "aarch64" "Simulator"')
    # Upstream collects symbols from the Intel simulator. For tvOS use the
    # arm64 device baseline, whose module list also exists in its simulator.
    replace('elif [ "$BUILD_SIMULATOR" = "yes" ]; then\n        arch="x86_64"',
            'elif [ "$BUILD_SIMULATOR" = "yes" ] && [ "$OSSTYLE" != "AppleTV" ]; then\n        arch="x86_64"')
    replace('    export VLCSDKROOT=$SDKROOT', '    export VLCSDKROOT=$SDKROOT\n    export -n SDKROOT')
    replace('    echo \"EXTRA_CFLAGS += ${EXTRA_CFLAGS}\" >> config.mak',
            '    echo \"SDKROOT := $SDKROOT\" >> config.mak\n    echo \"EXTRA_CFLAGS += ${EXTRA_CFLAGS}\" >> config.mak')
    replace('    export USE_FFMPEG=1', '''    # Resolve the matching target before contrib/configure, never host FFmpeg.
    case "$OSSTYLE:$PLATFORM" in
        MacOSX:*) opx_target="macos-$ACTUAL_ARCH" ;;
        iPhone:OS) opx_target="ios-$ACTUAL_ARCH" ;;
        iPhone:Simulator) opx_target="ios-sim-$ACTUAL_ARCH" ;;
        AppleTV:OS) opx_target="tvos-$ACTUAL_ARCH" ;;
        AppleTV:Simulator) opx_target="tvos-sim-$ACTUAL_ARCH" ;;
    esac
    opx_ffmpeg="$OPX_FFMPEG_PACKAGE/third_party/ffmpeg/$opx_target"
    test -f "$opx_ffmpeg/lib/pkgconfig/libavcodec.pc"
    export OPX_FFMPEG_PKGCONFIG="$opx_ffmpeg/lib/pkgconfig"
    export PKG_CONFIG_PATH="$OPX_FFMPEG_PKGCONFIG"
    export PKG_CONFIG_LIBDIR="$OPX_FFMPEG_PKGCONFIG"
    export USE_FFMPEG=1''')
    replace('--prefix=${VLCROOT}/contrib/${OSSTYLE}${PLATFORM_IDENTIFIER}-${HOST_TRIPLET}-${ARCH} --disable-gpl',
            '--prefix=${VLCROOT}/contrib/${OSSTYLE}${PLATFORM_IDENTIFIER}-${HOST_TRIPLET}-${ARCH} --disable-ffmpeg')
    replace('        --enable-ad-clauses', '        --disable-x264 --disable-x265 --disable-x262 --disable-postproc --disable-a52 --disable-dca --disable-faad2')
    # Upstream relies on /bin/sh's escape-expanding echo; use explicit printf
    # so module declarations and xcconfig assignments are real separate lines.
    replace('echo "$DEFINITIONS\\n$BUILTINS"',
            "printf '%b\\n' \"$DEFINITIONS\\n$BUILTINS\"")
    replace('echo "VLC_PLUGINS_DEVICE_LDFLAGS=$DEVICELDFLAGS\\nVLC_PLUGINS_SIMULATOR_LDFLAGS=$SIMULATORLDFLAGS"',
            "printf '%b\\n' \"VLC_PLUGINS_DEVICE_LDFLAGS=$DEVICELDFLAGS\\nVLC_PLUGINS_SIMULATOR_LDFLAGS=$SIMULATORLDFLAGS\"")
    replace('    spopd # vlc\n}', '''    for spec in macosx:macos:arm64 macosx:macos:x86_64 iphoneos:ios:arm64 iphonesimulator:ios-sim:arm64 iphonesimulator:ios-sim:x86_64 appletvos:tvos:arm64 appletvsimulator:tvos-sim:arm64; do
        IFS=: read -r opx_sdk opx_platform opx_arch <<< "$spec"
        echo "OPX_FFMPEG_LDFLAGS[sdk=$opx_sdk*][arch=$opx_arch] = -L\\"$OPX_FFMPEG_PACKAGE/third_party/ffmpeg/$opx_platform-$opx_arch/lib\\" -lavcodec -lavformat -lavutil -lswscale -lswresample -lavfilter" >> "$PROJECT_DIR/Resources/MobileVLCKit/vlc-plugins-$OSSTYLE.xcconfig"
    done
    spopd # vlc
}''')
    replace('    # add this after the contrib step', '    # A managed cache may contain archives from the old contrib recipe.\n    # Only shared package-ffmpeg libraries may reach the final framework.\n    opx_contrib="$VLCROOT/contrib/$OSSTYLE$PLATFORM_IDENTIFIER-$HOST_TRIPLET-$ARCH"\n    rm -f "$opx_contrib"/lib/libav*.a "$opx_contrib"/lib/libsw*.a\n    rm -f "$opx_contrib"/lib/pkgconfig/libav*.pc "$opx_contrib"/lib/pkgconfig/libsw*.pc\n    rm -rf "$opx_contrib"/include/libav* "$opx_contrib"/include/libsw*\n\n    # add this after the contrib step')
    replace('    make install > ${out}', '    rm -rf "$PREFIX/lib/vlc/plugins"\n    make install > ${out}')
    replace('    ARCH="$1"', '    ARCH="$1"\n    export CC="$(xcrun --find clang)"\n    export CXX="$(xcrun --find clang++)"\n    export OBJC="$CC"\n    export OBJCXX="$CXX"')
    replace('               SKIP_INSTALL=no', '               MACOSX_DEPLOYMENT_TARGET=12.0 \\\n               TVOS_DEPLOYMENT_TARGET=15.0 \\\n               CODE_SIGNING_ALLOWED=NO \\\n               OTHER_LDFLAGS=\'$(inherited) $(OPX_FFMPEG_LDFLAGS)\' \\\n               SKIP_INSTALL=no')
    # Mobile framework targets do not inherit the StaticLibVLC xcconfig.
    # Supply the owner's path at archive scope, expanded per architecture.
    replace('    xcodebuild archive', '''    case "$PLATFORM" in
        macosx) opx_link_platform=macos ;;
        iphoneos) opx_link_platform=ios ;;
        iphonesimulator) opx_link_platform=ios-sim ;;
        appletvos) opx_link_platform=tvos ;;
        appletvsimulator) opx_link_platform=tvos-sim ;;
    esac
    xcodebuild archive''')
    script = script.replace("OTHER_LDFLAGS='$(inherited) $(OPX_FFMPEG_LDFLAGS)'",
        'OTHER_LDFLAGS="\\$(inherited) -L$OPX_FFMPEG_PACKAGE/third_party/ffmpeg/$opx_link_platform-\\$(CURRENT_ARCH)/lib -lavcodec -lavformat -lavutil -lswscale -lswresample -lavfilter"')
    # Modern Xcode requires an explicit SDK/deployment target in compiler commands.
    replace('    ${VLCROOT}/configure \\\n', '''    export CC="$CC $EXTRA_CFLAGS"
    export CXX="$CXX $EXTRA_CFLAGS"
    export OBJC="$OBJC $EXTRA_CFLAGS"
    export OBJCXX="$OBJCXX $EXTRA_CFLAGS"
    ${VLCROOT}/configure \\
''')
    write_if_changed(root / 'buildMobileVLCKit.sh', script)
    main = root / 'libvlc/vlc/contrib/src/main.mak'
    text = main.read_text()
    text = text.replace('PKG_CONFIG_PATH := /usr/share/pkgconfig',
                        'PKG_CONFIG_PATH := $(OPX_FFMPEG_PKGCONFIG)')
    text = text.replace('MESONBUILD = meson compile -C $</build $(MESON_BUILD) $(MESONCOMPILEFLAGS) && meson install -C $</build',
                        'MESONBUILD = meson compile -C $</build -j $(MAKE_JOBS) $(MESON_BUILD) $(MESONCOMPILEFLAGS) && meson install --no-rebuild -C $</build')
    text = text.replace('download = curl -f -L', 'download = curl -sS -f -L')
    write_if_changed(main, text)
    ffmpeg = root / 'libvlc/vlc/contrib/src/ffmpeg/rules.mak'
    text = ffmpeg.read_text()
    marker = '# OpenPlayX: provided by package-ffmpeg, including SoXR dependencies.'
    if marker not in text:
        text += '\n' + marker + '\nPKGS_FOUND += ffmpeg\nDEPS_ffmpeg :=\n'
    write_if_changed(ffmpeg, text)



if __name__ == '__main__':
    patch(Path(sys.argv[1]).resolve())
