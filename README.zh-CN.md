# openplayx_playback（package-libvlc）

[English](README.md) | 简体中文

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[OpenPlayX](https://github.com/openplayx/openplayx) 的 libVLC 播放封装。播放集成测试统一维护在 package-media。

```
OpenPlayX App → PlayerBackend（lib/playback.dart）→ LibVlcBackend → vlc_player 2.1.2 → libVLC（Apple 平台为 VLCKit 3.7.3）
```

`vlc_player` 精确锁定版本：格式测试结果只代表某一个 libVLC 构建，App 与本测试必须解析到同一版本。

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

MIT，见 [LICENSE](LICENSE)。libVLC 与 VLCKit 适用其各自（LGPL）条款。
