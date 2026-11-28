# openplayx_playback（package-libvlc）

[English](README.md) | 简体中文

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[OpenPlayX](https://github.com/openplayx/openplayx) 的 libVLC 播放封装。播放集成测试统一维护在 package-media。

```
OpenPlayX App → PlayerBackend（lib/playback.dart）→ LibVlcBackend → vlc_player 2.1.2（本地 fork）→ libVLC / VLCKit
```

`vlc_player` 使用 `forks/vlc_player`，保留 2.1.2 的 Dart API。Apple 原生库由本包从固定源码构建，
macOS / iOS / tvOS 链接 `package-ffmpeg` 的共享 FFmpeg，与媒体处理桥和 libmpv 共用同一套库。
Android / Linux / Windows 同样从固定源码构建 libVLC，链接 package-ffmpeg 的共享库；不再回退到 Maven AAR、官方预编译运行库或系统 libVLC。

## Apple 原生构建

同级目录需要 `ffmpeg-package`（可用 `OPX_FFMPEG_PACKAGE` 指定其他路径）。
`pod install` 自动执行 `tool/ensure_vlckit_apple.sh macos|ios|tvos`，先构建 FFmpeg，
再构建 VLCKit，并生成 `<platform>/Frameworks/*.xcframework`。需要 Xcode、Git、Python 3、
make、CMake、pkg-config 和网络；缺失的上游构建工具由 VLC 的 tools 配方安装到构建缓存。
首次构建较慢，后续用源码版本、构建配方和 FFmpeg 指纹判断是否需要重新构建。

固定源码在 `tool/vlc-sources.env`，完整应用 VLCKit 官方的 VLC 补丁集。
`tool/patch_vlckit.py` 禁用 contrib 的 FFmpeg 构建，将目标架构对应的头文件和共享库用于编译、链接。
`tool/verify_vlckit.py` 将动态库引用映射到 App 的 Av*/Sw* frameworks，
逐个检查产物切片的链接关系及静态 FFmpeg 符号，检查失败时不会安装产物。
构建日志位于 `build/vlckit-<platform>.log`，源码缓存位于 `third_party/`。

```sh
bash tool/ensure_vlckit_apple.sh macos
python3 tool/verify_vlckit.py macos/Frameworks/VLCKit.xcframework
```

2026-11-26 已验证 macOS arm64 / x86_64 框架构建及逐架构共享库检查。
arm64 App 的 `integration_test/ffmpeg_bridge_test.dart` 验证了 libVLC 强制软件解码后，
FFmpeg 媒体处理桥仍可探测、截图；7 个格式回归（H.264、HEVC、VP9、AV1、MP3、Ogg/FLAC、Vorbis）通过。
2026-11-27，iOS 真机 arm64 与模拟器 arm64 / x86_64 框架也已构建并通过共享库检查。iOS 与 Android 的 7 个格式回归均通过；Android 三种 ABI 的原生产物检查均通过。tvOS 真机 / 模拟器 arm64 框架通过检查，模拟器完成了 avcodec 软件解码后同进程 FFmpeg 探测、截图。Linux arm64 在不安装系统 libVLC 的镜像通过原生依赖检查及 7 个格式回归。Windows 和 Linux x86_64 仍需对应主机的构建与运行验证。

## Android / Linux / Windows 原生构建

| 平台 | 构建入口 | 打包方式 |
| --- | --- | --- |
| Android（arm64-v8a / armeabi-v7a / x86_64） | `tool/ensure_libvlc_android.sh [abi...]`，由 Gradle 配置阶段调用 | 自建官方 Java/JNI 和 libvlc.so；FFmpeg 的 .so 只由 package-ffmpeg 打包。需要 NDK 27+，最低 API 29。 |
| Linux（arm64 / x86_64） | `tool/build_libvlc.sh linux-arm64\|linux-x86_64`，由插件 CMake 调用 | 自建核心库放入 bundle/lib，VLC 插件保留在 lib/vlc/plugins；不链接系统 libVLC。桌面 SDK 仍使用系统库。需要 CMake 3.19+ 和 GTK / XCB / PulseAudio / ALSA 开发包（见 Linux Dockerfile）。 |
| Windows（x86_64） | MSYS2 / MinGW-w64 下运行 `tool/build_libvlc.sh windows-x86_64`，由 CMake 调用 | 自建 libvlc.dll、libvlccore.dll 和 plugins；MSVC 插件通过 COFF 导入库链接；FFmpeg DLL 由 package-ffmpeg 打包。 |

Android Java/JNI 与核心源码版本同样固定在 `tool/vlc-sources.env`，应用官方补丁集。
`third_party/libvlc/<target>` 的缓存键包含 VLC 构建配方和 FFmpeg 配方。
`tool/verify_libvlc.py` 检查 ELF / PE 实际导入是否匹配 package-ffmpeg 的 ABI，
拒绝静态或私有 FFmpeg 副本，并检查 Linux 的间接依赖，防止引入系统 FFmpeg。
Windows CI 对两个播放引擎运行回归；Linux AppImage 打包保留自建插件并拒绝第二套 FFmpeg ABI。

```sh
ANDROID_NDK_HOME=/path/to/ndk bash tool/ensure_libvlc_android.sh arm64-v8a
bash tool/build_libvlc.sh linux-arm64       # 在对应架构的 Linux 主机运行
bash tool/build_libvlc.sh windows-x86_64    # 在 MSYS2 中运行
```

桌面构建入口自动逐包检查 contrib，保留已通过的结果。可用 `OPX_VLC_BUILD_DIR` 将主库对象保存在工作区清理范围以外。只有编译器、源码或全局编译参数变化才清理主库对象；依赖配方变化只重建受影响的包，并用已有对象重新链接插件。

在空闲、已 bootstrap 的 contrib 缓存上，也可用与原构建相同的编译环境单独检查：

```sh
CFLAGS='-O2 -g -std=gnu17' python3 -X utf8 tool/check_vlc_contrib.py --directory "$OPX_VLC_SOURCE_DIR/contrib/opx-windows-x86_64" --report build/dependency-checks --adopt-existing
CFLAGS='-O2 -g -std=gnu17' python3 -X utf8 tool/check_vlc_contrib.py --directory "$OPX_VLC_SOURCE_DIR/contrib/opx-windows-x86_64" --report build/sid-check --only sidplay2
```

仅在首次接管已验证过的旧缓存时使用 `--adopt-existing`。每个包有独立日志，
`summary.json` 逐项记录结果，首次失败即停止；恢复时保留已通过的包。
`--rebuild sidplay2` 或包配方变化只使该包及其依赖方失效，不清空其他包。
编译器或配置变化需要独立源码缓存。系统提供的库不在这里重编，最终 DLL / ELF
依赖检查和播放冒烟仍需分别通过。

## 使用

App 以同级目录 path 依赖引用（CI 以 `package-libvlc` companion 检出）：

```yaml
dependencies:
  openplayx_playback:
    path: ../package-libvlc
```

```dart
final backend = LibVlcBackend();          // 每个实例一个原生播放器
PlayerVideoView(backend: backend);        // 先挂载视频视图
await backend.open(Uri.file(path));       // 自动播放
backend.value;                            // 状态、进度、时长、视频尺寸……
await backend.getStats();                 // 解码统计（画面、音频块）
backend.dispose();
```

`LibVlcBackend(extraOptions: [...])` 追加 libVLC 实例参数；格式测试用它把解码后的音频写入文件。

## 文件格式播放测试

播放集成测试、样本清单、素材准备脚本和报告生成统一维护在
[package-media](https://github.com/openplayx/package-media/blob/main/README.zh-CN.md#文件格式播放测试)，使用 libVLC 引擎运行：

```sh
cd ../package-media
bash tool/test_formats.sh --engine vlc
bash tool/test_formats.sh --engine vlc --pack --only 'pack-*'
```

报告默认写入 package-media 的 `build/formats/`，可用 `OPX_REPORT_DIR` 指定。

[素材准备和检查说明](https://github.com/openplayx/package-media/blob/main/formats/README.md)。适配器单元测试仍在本仓库，通过 `flutter test` 运行。

## 开发

```sh
flutter analyze                           # 播放封装
(cd example && flutter analyze)           # 示例宿主 App
```

## 许可

MIT，见 [LICENSE](LICENSE)。VLC / VLCKit 保留其原始许可；本包所有平台的原生产物链接 package-ffmpeg 的 GPL 扩展构建，按 GPL 组合记录。Apple 原生许可随构建产物保存在 Frameworks/。
