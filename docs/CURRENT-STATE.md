# 当前状态（2026-11-25）

**2026-11-25：全局 Linux GPU 入口已切到 r3.6 Linux 候选；现存应用进程仍可能映射 r3.5。Termux:X11 目前前端和 server 同映射旧的 r3.6 输入候选 APK；最新 rc1 APK 尚未安装，需安全切换会话。r3.6 正式验收仍未完成。** 快速蓝牙鼠标仍有用户报告的跳动，不能把候选改名 final 当作修复。

## 唯一运行身份

| 对象 | 当前值 |
|---|---|
| 设备 | Xiaomi Pad 7S Pro / 25053RP5CC |
| 本次回读系统 | Android 17 / API 37 / OS4.0.5.0.XOTCNXM |
| 全局 Linux GPU 入口 | `/opt/pad7spro-gpu-r36-20261125`；`release.json` 为 `r3.6-linux-candidate`（已激活，非正式版） |
| 统一入口 | `/usr/local/bin/gpu-run`、`gpu-launcher` |
| WSI SHA-256 | `d011bb7b220ab83bfb7c136e1e1b3190def27c013cb24775167c405073d77636` |
| 已安装 X11 / 前端与 server 映射 | `1.03.01-d55f1b7-gpu-r3.6-cursor-input-candidate`；两进程映射同一 APK `5aed79535688e4abb65eeb485de65fe2fdebe243911b98123b4d06e94b93996d` |
| 新 X11 rc1 APK | `build/r3.6-rc1-clean-20261111/candidate.apk`，SHA `b5f92532382d60f4b3bc3ddedfc0ff79c5538614a8da6443afcccbfd30b7c9f0`；已备份当前安装包，尚未替换 |
| 本轮新构建 | `1.03.01-d55f1b7-gpu-r3.6-rc1`；未安装，完整哈希见发布证据 |
| 显示与输入 | 原生分辨率，上限 120；相对捕获临时为 true，效果未验收 |

本轮现场 PID 与 APK maps 已重新读取；APK 仍未替换，Termux:X11 与桌面未重启。新入口仅影响之后启动的应用，已经运行的进程保留旧映射。

## 2026-11-25 Linux r3.6 候选已激活

- 新候选前缀：`/opt/pad7spro-gpu-r36-20261125`；构建目录：`build/r3.6-linux-20261125/`。由锁定源码在 aarch64 fresh build，使用 `scripts/install.sh` 以独立前缀安装。
- `gpu-run doctor`、`run-gpu --headless probe` 和 `gpu-run ahb` 报告 `AHB_ALLOCATE_SEND_RECEIVE_READBACK_RELEASE_OK`，`probe-present --motion` 已通过；探针识别 `Mali-G925-Immortalis` 并报告 `VULKAN_DEVICE_SUBMIT_READBACK_OK`、`VULKAN_SWAPCHAIN_RECREATE_PRESENT_OK`。
- 已通过 `scripts/activate-release.py` 原子切换 `/usr/local/bin/{gpu-run,gpu-launcher,run-gpu,gpu-env}`，同步 Termux 启动脚本，备份在 `/opt/cc-switch-update-helper/backups/r3.6-activation-20261125/`。已有应用进程仍映射其启动时加载的 r3.5 库；当前 CC Switch PID 28967 仍映射旧前缀。没有停止桌面。
- 当前 Termux:X11 前端 PID 13590 与 server PID 13550 都映射已安装的 `5aed7953…` APK。最新锁定 0015–0017 的 rc1 APK `b5f92532…` 已核验签名证书并备份当前 APK，但未替换/重启；安装需要安全会话窗口。
- 详细实现路线、透明度处理边界和新 chroot 复现步骤见 [r3.6 实现路线](r3.6-implementation-plan.md)；构建证据见 `evidence/r3.6-linux-candidate-20261125.json`；激活及当前映射证据见 `evidence/r3.6-deployment-20261125.json`。

## 2026-11-25 通用入口补充

- 新增 `bin/run-gpu` 与 `bin/gpu-env`，并建立对应系统链接；初始安装在 r3.5，随后已由 r3.6 激活事务切换到新前缀。原始备份在 `/opt/cc-switch-update-helper/backups/gpu-common-env-20261125/`，r3.6 激活备份见上文。`run-gpu 应用 参数` 默认使用 auto 硬件路由；`source /usr/local/bin/gpu-env` 导出共用 Vulkan/Zink/Mali 环境。
- 新 chroot 可使用 `scripts/install-global-env.sh` 安装 Bash 登录 profile hook；默认仅预览，写入时必须指定新备份目录。
- 当前 XFCE 会话早已从 `gpu-run gl ... startxfce4` 继承 r3.5 Vulkan/Zink/Mali 环境，本次没有重启会话。`gpu-env` 把同一套公共变量显式化，供新 chroot 的桌面会话和登录 shell 复用；WebKit preload 与 Electron 参数仍按应用单独处理。
- 入口可让后续启动的普通 Vulkan/Zink 客户端继承 Mali 环境；需专用启动参数或本身使用 CPU 绘制的应用仍需适配与实测。现存 XFCE/应用进程不会热加载新前缀；需在安全时段正常重启相应会话/应用。

## 本轮收敛

- X11 固定基线加 0015 独立 SurfaceControl 光标及空 state 防护、0016 光标独立唤醒、0017 Android 鼠标源无缓冲分发，全部进入 `sources.lock.json`，不再依赖手工拼装候选源码。
- Linux WSI 保持 0012，不纳入 Writer 退出崩溃实验。保留真实 Mali、Skia Vulkan / ANGLE Vulkan / Zink 路径和统一 gpu-run，没有自动 CPU 回退。
- Fcitx5 已运行时跳过；Clipman 禁用重复 XDG 项并检查已有 D-Bus 实例。本轮纠正 `TryExec` 格式，保留剪贴板内容。
- Termux 启动器支持 HOME/PREFIX/rootfs 配置；工具可创建缺失入口、保存原件、检查冲突并回退。取消启动期间重复重启 adbd；ADB 观察失败仍不能触发桌面清理。

## 验收边界

- 历史 r3.5：native 提交约 117/s，默认 Chromium 约 112–116 rAF/s；712704 个物理像素零差异。这不是当前鼠标物理 FPS。
- 独立光标已有实机样本证明移动、换形、隐藏可不增加主 Surface 整帧绘制；主帧门控、拷贝顺序、空 state、光标唤醒回归通过。不能由此宣称降低整机功耗或达到物理 120 FPS。
- 鼠标第一包用户反馈部分改善，第二包反馈与第一包无区别；实际输入曾有约 91 ms 坐标停顿，期间内核仍收到移动。相对捕获后样本不是受控 A/B，仍未验收。
- Greezer 曾冻结 Termux/Widget 共享 UID；Widget 的 PowerKeeper `noRestrict` 曾重置，长期防冻结、锁屏恢复和续航未验收。
- 隔离 HOME 迁移测试通过；没有卸载当前 Termux或完成干净设备端到端验收。保留 rootfs 的快捷接入与恢复出厂后的从零安装必须区分。

## 文档入口

- [安装与更换 Termux](setup.md)：快捷入口 `scripts/bootstrap-termux.sh`。
- [r3.6 发布说明与架构审查](r3.6-release.md)、[机器证据](../evidence/r3.6-release-preparation-2026-11-11.json)。
- [维护与回退](tablet-handoff.md)。
- 历史事实：[研发记录](r3.6-development.md)、[鼠标证据](../evidence/r3.6-cursor-independent-wake-2026-11-11.json)、[OS4 稳定性](os4-stability-2026-11-10.md)、[r3.5 定版](r3.5-efficiency.md)。
- [整理前全文](history/2026-11-11-CURRENT-STATE-before-release-consolidation.md)。历史 APK、CSV、trace 不改值。

APK 切换先准备、校验、备份并由用户安排安全会话切换；不得全局 pkill 或自动重启 Termux。正式状态以证据为准，不能根据文件名推断。
