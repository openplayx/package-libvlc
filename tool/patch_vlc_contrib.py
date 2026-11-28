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

    # Nettle 4 always writes the complete SHA-1 digest and removed its length
    # argument. SHA1_Final also promises a full digest when passed a pointer.
    old_final = '#define SHA1_Final(a,b) sha1_digest(b, sizeof(a), a)'
    new_final = ('#if NETTLE_VERSION_MAJOR >= 4\n'
                 '#define SHA1_Final(a,b) sha1_digest(b, a)\n'
                 '#else\n'
                 '#define SHA1_Final(a,b) sha1_digest(b, SHA1_DIGEST_SIZE, a)\n'
                 '#endif')
    port = source / 'contrib/src/asdcplib/port-to-nettle.patch'
    text = port.read_text()
    if '+' + old_final in text:
        text = text.replace('@@ -0,0 +1,14 @@\n+#include <nettle/aes.h>',
                            '@@ -0,0 +1,19 @@\n+#include <nettle/version.h>\n+#include <nettle/aes.h>')
        port.write_text(text.replace('+' + old_final,
                                    '\n'.join('+' + line for line in new_final.splitlines())))
    for header in source.glob('contrib/*/asdcplib/src/nettle_map.h'):
        text = header.read_text()
        if old_final in text:
            header.write_text('#include <nettle/version.h>\n' + text.replace(old_final, new_final))

    # Regex's old Makefile hardcodes CFLAGS instead of using configure's value.
    regex = source / 'contrib/src/regex/rules.mak'
    text = regex.read_text()
    old = '\t+$(MAKEBUILD) subirs=\n'
    if old in text:
        regex.write_text(text.replace(old, '\t+$(MAKEBUILD) subirs= CFLAGS="$(CFLAGS)"\n'))

    # SID's byte lookup tables assume signed char, as on its original x86
    # targets. Preserve those values on ARM instead of dropping SID support.
    sid = source / 'contrib/src/sidplay2/rules.mak'
    text = sid.read_text()
    old = 'cd $< && $(HOSTVARS) ./configure $(HOSTCONF)'
    if old in text:
        sid.write_text(text.replace(old, 'cd $< && $(HOSTVARS) CXXFLAGS="$(CXXFLAGS) -fsigned-char" ./configure $(HOSTCONF)'))
    # MSYS2 ln copies when native symlinks are unavailable. The alias must
    # wait for its libtool archive instead of racing the parallel build.
    sid_patch = source / 'contrib/src/sidplay2/opx-resid-alias-dependency.patch'
    sid_patch.write_text('--- a/resid/Makefile.am\n+++ b/resid/Makefile.am\n@@ -10,7 +10,7 @@\n noinst_LTLIBRARIES = libresidc.la\n noinst_HEADERS = $(resid_headers)\n \n-all-local:\n+all-local: libresidc.la\n \tln -sf libresidc.la libresid.la\n \n endif\n')
    text = sid.read_text()
    line = '\t$(APPLY) $(SRC)/sidplay2/opx-resid-alias-dependency.patch'
    if line not in text:
        sid.write_text(text.replace('\t$(MOVE)', line + '\n\t$(MOVE)'))
    for makefile in source.glob('contrib/*/sidplay-libs/resid/Makefile.am'):
        text = makefile.read_text()
        fixed = text.replace('all-local:\n', 'all-local: libresidc.la\n')
        if fixed != text:
            makefile.write_text(fixed)

    # VLC's Windows plugins link mysofa statically. Its generated export
    # header otherwise emits DLL import references from libspatialaudio.a.
    spatial = source / 'contrib/src/spatialaudio/rules.mak'
    text = spatial.read_text()
    marker = '# OpenPlayX: static mysofa consumer on Windows.'
    if marker not in text:
        spatial.write_text(text + '\n' + marker + '\nifdef HAVE_WIN32\n'
                           'SPATIALAUDIO_CONF += -DCMAKE_CXX_FLAGS="$(CXXFLAGS) -DMYSOFA_STATIC"\n'
                           'endif\n')
    # FindZLIB otherwise prefers the system import archive. libarchive then
    # emits ZLIB_DLL imports, while VLC's plugin links the static zlib archive.
    archive = source / 'contrib/src/libarchive/rules.mak'
    text = archive.read_text()
    marker = '# OpenPlayX: static zlib consumer on Windows.'
    if marker not in text:
        archive.write_text(text + '\n' + marker + '\nifdef HAVE_WIN32\n'
                           'LIBARCHIVE_CONF += -DZLIB_USE_STATIC_LIBS=ON\n'
                           'endif\n')
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
