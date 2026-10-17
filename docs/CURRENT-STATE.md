# 当前版本：r3.5 最终定版

2026-10-17：用户明确以当前结果作为 **r3.5 最终版本**，发行标识 `r3.5-final-20261017`。本轮优化已收尾；未达到稳定真实 120 帧、长期功耗/输入延迟等项目作为已知限制保留，不再自动执行旧计划或更换 APK。

| 项目 | 定版值 |
|---|---|
| 发行版 / 标识 | r3.5 / `r3.5-final-20261017` |
| 已部署 Linux 前缀 | `/opt/pad7spro-gpu-fps-20261017`（保留既有 RUNPATH，不改目录名） |
| 统一入口 | `/usr/local/bin/gpu-run`、`gpu-launcher` 指向上述前缀 |
| Termux:X11 APK SHA-256 | `88346b5831c33e585d467bbf0f8255b972a05dca1ffb112a03bf683404625411` |
| WSI 库 SHA-256 | `d011bb7b220ab83bfb7c136e1e1b3190def27c013cb24775167c405073d77636` |
| 默认渲染 | Skia 原生 Vulkan；WebGL ANGLE Vulkan；GL Zink；原厂 Mali-G925 |
| 默认显示配置 | 原生分辨率；X11 / WSI 上限 120；BGRA；诊断默认关闭 |
| 已纳入补丁 | Termux:X11 至 0014，WSI 至 0012，完整顺序以 `sources.lock.json` 为准 |

Android versionName 仍为 `1.03.01-d55f1b7-gpu-r3.5-repro`，用完整哈希识别；定版仅整理版本元数据与归档，不重编、不安装、不重启。

## 已验证结果与边界

| 最终样本 | 结果 | 解释范围 |
|---|---|---|
| 1200 帧 native 探针 | 117.01 次提交/秒 | 无追踪；不是屏幕新内容计数 |
| 默认 Chromium canvas / scroll / edit | 112.79 / 115.51 / 111.74 rAF/s | 原生 Vulkan、Mali、私有测试 profile |
| 单独 GPU copy 比例 | 旧诊断 113/647（17.47%）→ 3/639（0.47%） | 跨重启诊断；不作严格 A/B 帧率/功耗归因 |
| 遮挡 / 增量 / 空区域 | 712704 个物理像素，0 差异 | 最终图案正确性；不是逐帧像素解码 |
| 显式 ACK 参数、3000 帧 | 119.79 rAF/s；显示新来源关联约 105.52/s | app-tags 采样、约 24.93 秒；该参数未加入默认入口 |

**稳定真实页面 120 帧未被证实；长期温升/续航、整机节能幅度、精确输入延迟、视频硬解及其他机型/全新 rootfs 均未因此获得保证。** 既往失败、旧 APK、CSV 和原始日志不改数值。

## 文档与证据

- [r3.5 定版说明与历史实现](r3.5-efficiency.md)
- [平板接手与回退](tablet-handoff.md)
- [最终版本清单](../evidence/r3.5-final-2026-10-17.json)
- [0014 完整安装及验收](../evidence/deferred-copy-wake-2026-10-17.json)
- [前一轮 FPS 修复](../evidence/fps120-release-2026-10-17.json) / [显示许可与提交诊断](../evidence/display-permit-surface-submit-2026-10-17.json)
- [定版前逐轮状态](history/2026-10-17-current-state-before-final.md)

数据位置：公开证据和校验在 `evidence/`、`evidence/SHA256SUMS`；原始 CSV/JSON/trace/截图与 APK 仍保留在 `build/`。另有仓库外本地归档 `/opt/pad7spro-gpu-release-test/releases/r3.5-final-20261017/`，包含源码快照、最终 APK、Linux 前缀、原始数据清单和压缩包、SHA256SUMS。该归档是本机私有备份，不自动发布到互联网；不含用户 profile、SDK 缓存或签名私钥。

## 后续约定

- `NoCompositorFrameAcks`、Graphite、optimal AHB 和 buffer-age 原型等实验没有因本次定版被开启。
- 正常启动和 Widget 保持现有参数、用户配置、权限及会话；硬件失败不自动切 CPU。
- APK 替换曾中断当前对话，后续如有新的明确需求，仍须先保存工作、通知用户并由用户安排重启；不得全局 pkill 或自行停止桌面。
- `src/probe-present.c` 原有未提交实验保持原样，未纳入定版提交；另外保存差异备份。
