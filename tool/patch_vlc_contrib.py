#!/usr/bin/env python3
"""Use package-ffmpeg for contrib dependencies too (notably SoXR)."""
from pathlib import Path
import sys


def patch(source: Path):
    main = source / 'contrib/src/main.mak'
    text = main.read_text().replace('PKG_CONFIG_PATH := /usr/share/pkgconfig',
                                    'PKG_CONFIG_PATH := $(OPX_FFMPEG_PKGCONFIG)')
    text = text.replace('MESONBUILD = meson compile -C $</build $(MESON_BUILD) $(MESONCOMPILEFLAGS) && meson install -C $</build',
                        'MESONBUILD = meson compile -C $</build -j $(OPX_BUILD_JOBS) $(MESON_BUILD) $(MESONCOMPILEFLAGS) && meson install --no-rebuild -C $</build')
    text = text.replace('download = curl -f -L', 'download = curl -sS -f -L')
    if main.read_text() != text:
        main.write_text(text)
    rule = source / 'contrib/src/ffmpeg/rules.mak'
    text = rule.read_text()
    marker = '# OpenPlayX: FFmpeg is supplied by package-ffmpeg.'
    if marker not in text:
        rule.write_text(text + '\n' + marker + '\nPKGS_FOUND += ffmpeg\nDEPS_ffmpeg :=\n')

    # MSYS2 emulates symlinks by copying their targets. FluidLite's unused
    # example/FluidLite -> .. link recurses into itself during extraction.
    # Keep every library source file while omitting only that example link.
    fluidlite = source / 'contrib/src/fluidlite/rules.mak'
    text = fluidlite.read_text()
    unpack = "\t$(RM) -R $@ $(UNPACK_DIR) && tar --exclude='$(UNPACK_DIR)/example/FluidLite' -xJof $<"
    if '\t$(UNPACK)\n' in text:
        fluidlite.write_text(text.replace('\t$(UNPACK)\n', unpack + '\n'))

    # The upstream tarball also contains a test MP3 link to its author's
    # /home/ec2-user directory. It is neither shipped nor used by the library.
    live555 = source / 'contrib/src/live555/rules.mak'
    text = live555.read_text()
    unpack = "\t$(RM) -R $@ $(UNPACK_DIR) && tar --exclude='live/testProgs/whiteroom.mp3' -xzof $<"
    if '\t$(UNPACK)\n' in text:
        live555.write_text(text.replace('\t$(UNPACK)\n', unpack + '\n'))

    # SID's byte lookup tables assume signed char, as on its original x86
    # targets. Preserve those values on ARM instead of dropping SID support.
    sid = source / 'contrib/src/sidplay2/rules.mak'
    text = sid.read_text()
    old = 'cd $< && $(HOSTVARS) ./configure $(HOSTCONF)'
    if old in text:
        sid.write_text(text.replace(old, 'cd $< && $(HOSTVARS) CXXFLAGS="$(CXXFLAGS) -fsigned-char" ./configure $(HOSTCONF)'))
    # CMake's host FPU query reports false for native Linux AArch64. The
    # selected NEON64 decoder requires floating point on every ARM64 target.
    mpg_patch = source / 'contrib/src/mpg123/opx-arm64-fpu.patch'
    mpg_patch.write_text('--- a/ports/cmake/src/CMakeLists.txt\n+++ b/ports/cmake/src/CMakeLists.txt\n@@ -196,7 +196,7 @@\n check_cpu_arch_arm32(ARCH_IS_ARM32)\n check_cpu_arch_arm64(ARCH_IS_ARM64)\n \n-if(WIN32 OR (ARCH_IS_ARM64 AND APPLE))\n+if(WIN32 OR ARCH_IS_ARM64)\n     set(HAVE_FPU 1)\n else()\n     cmake_host_system_information(RESULT HAVE_FPU QUERY HAS_FPU)\n')
    rule = source / 'contrib/src/mpg123/rules.mak'
    text = rule.read_text()
    line = '\t$(APPLY) $(SRC)/mpg123/opx-arm64-fpu.patch'
    if line not in text:
        rule.write_text(text.replace('\t$(MOVE)', line + '\n\t$(MOVE)'))
    for cmake in source.glob('contrib/*/mpg123/ports/cmake/src/CMakeLists.txt'):
        text = cmake.read_text()
        fixed = text.replace('if(WIN32 OR (ARCH_IS_ARM64 AND APPLE))', 'if(WIN32 OR ARCH_IS_ARM64)')
        if text != fixed:
            cmake.write_text(fixed)


if __name__ == '__main__':
    patch(Path(sys.argv[1]))
