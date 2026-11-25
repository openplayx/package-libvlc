# openplayx_playback（package-libvlc）

[English](README.md) | 简体中文

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[OpenPlayX](https://github.com/openplayx/openplayx) 的 libVLC 播放封装，以及决定
OpenPlayX 能否宣称“支持某种格式”的文件格式播放测试。

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

**默认不运行**：不在 `test/` 下，App 的 CI 也不运行。仅当本仓库改动时运行：播放封装、`vlc_player` 版本、libVLC/VLCKit 构建或 `formats/`。

```sh
brew install ffmpeg                       # 生成素材与 ffprobe
tool/test_formats.sh                      # 全部样本，macOS
tool/test_formats.sh --only 'mp4-*,mp3'   # 按 ID 或通配符
tool/test_formats.sh --pack --only 'pack-*'  # 素材包样本（../openplayx-test/formats）
```

`--pack` 把 [openplayx-test](https://github.com/openplayx/openplayx-test) `formats/` 素材包（ALL-370）中的本地文件加为样本，命名为 `pack-<编号>-<扩展名>`，并标注 Linear 编号；期望值来自 ffprobe 和素材包的 440 Hz 正弦音。素材包的视频是动态测试图案，没有参考画面，这些样本不做截图比对。

运行结果写入 `build/formats/<时间戳>/report.md`（另有 `results.json`、截图和 Flutter 日志），有样本失败时以非零状态退出。

### 样本

[`formats/manifest.json`](formats/manifest.json) 列出样本及其验证的 Linear 任务。`tool/prepare_samples.py` 把样本准备到 `~/.cache/openplayx-libvlc-samples`（`OPX_SAMPLE_CACHE`），不提交到仓库：

- `generate`：用 ffmpeg 从 SMPTE 彩条（320×240，25 fps）和 1 kHz 立体声正弦音本地编码，6 秒。没有授权问题，且测试确切知道画面和声音应该是什么。
- `url` + `sha256`：下载（可重试、限大小）并校验。
- `playlist`：指向另一个样本的 pls/m3u/asx/cue 文件。

每个文件都用 ffprobe 检查，记录真实的封装和编码，而不是相信后缀。

### 检查内容

每个样本在 `example/` 宿主 App 里通过 `LibVlcBackend` 播放，结果对应与 OpenPlayX 相同的 libVLC 构建和参数：

| 检查 | 发现的问题 |
|---|---|
| 播放状态、进度前进 | 打不开、不起播 |
| 1 秒内的解码统计（异常时再测一次） | 黑屏、视频卡住或掉帧、音频卡住或丢失 |
| libVLC 识别到的轨道 | 缺视频轨或音轨 |
| 截图与 SMPTE 彩条对比（32×24 网格平均 RGB 差，阈值 24） | 花屏、绿屏/灰屏、颜色错误 |
| 用 libVLC `afile` 输出写下解码音频，与 1 kHz 正弦音比较音量和频率 | 无声、噪音、解码错误 |
| 时长和视频尺寸 | 时长或尺寸错误 |
| Seek 到中间并继续播到结尾 | Seek 失败、Seek 后提前结束 |

局限：彩条是静止画面，损坏只有落在关键帧上才看得出来（关键帧损坏的样本差异约 87，正常样本约 9）；截图是解码后的画面，不是 Flutter 实际渲染的结果（HDR 色调映射和屏幕颜色需另测）；`afile` 测的是解码音频，不是设备输出（直通需要功放设备）。

### 已知问题

- 同一进程中，前面的播放器会影响后面的播放器：已释放的播放器累计播放约 30 秒后（或播放过一个裸 `.m2v` 流后），后续视频会大量掉帧。因此测试每 6 个样本重启一次宿主 App（`OPX_BATCH`），并把失败的样本单独重跑一次；报告会标出只在单独运行时通过的样本。原因待查，App 在一次会话中连续播放多个视频时可能也受影响。

## 开发

```sh
flutter analyze                           # 播放封装
(cd example && flutter analyze)           # 宿主 App 与测试
```

## 许可

MIT，见 [LICENSE](LICENSE)。libVLC 与 VLCKit 适用其各自（LGPL）条款。
