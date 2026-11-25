# 当前状态（2026-11-25）

**2026-11-25：全局 Linux GPU 入口已切到 r3.6 Linux 候选；现场进程检查未发现仍映射 r3.5 bridge 的图形应用。Termux:X11 r3.6-rc1 APK 已安装，前端和 server 已重启并映射相同的新包。CC Switch 已在 r3.6 Linux 前缀下重新打开并验证实际进程映射。r3.6 正式验收仍未完成。** 快速蓝牙鼠标仍有用户报告的跳动，不能把候选改名 final 当作修复。

## 唯一运行身份

| 对象 | 当前值 |
|---|---|
| 设备 | Xiaomi Pad 7S Pro / 25053RP5CC |
| 本次回读系统 | Android 17 / API 37 / OS4.0.5.0.XOTCNXM |
| 全局 Linux GPU 入口 | `/opt/pad7spro-gpu-r36-20261125`；`release.json` 为 `r3.6-linux-candidate`（已激活，非正式版） |
| 统一入口 | `/usr/local/bin/gpu-run`、`gpu-launcher` |
| WSI SHA-256 | `d011bb7b220ab83bfb7c136e1e1b3190def27c013cb24775167c405073d77636` |
| 已安装 X11 / 前端与 server 映射 | `1.03.01-d55f1b7-gpu-r3.6-rc1`；两进程映射同一 APK `b5f92532382d60f4b3bc3ddedfc0ff79c5538614a8da6443afcccbfd30b7c9f0` |
| 当前 CC Switch | PID 28773，maps 含 r3.6 sysvk/libhybris/WSI、Mali 驱动及 Mesa EGL；窗口启动成功 |
| 当前 X11 APK | `1.03.01-d55f1b7-gpu-r3.6-rc1`；前端/server 均已映射，SHA `b5f92532382d60f4b3bc3ddedfc0ff79c5538614a8da6443afcccbfd30b7c9f0` |
| 显示与输入 | 原生分辨率，上限 120；相对捕获临时为 true，效果未验收 |

本轮 APK 已替换；Termux:X11 前端/server 新 PID 分别为 21872/21829，映射同一 APK inode。XFCE 已恢复。PID 为现场快照，之后需重新读取。

## 2026-11-25 Linux r3.6 候选已激活

- 新候选前缀：`/opt/pad7spro-gpu-r36-20261125`；构建目录：`build/r3.6-linux-20261125/`。由锁定源码在 aarch64 fresh build，使用 `scripts/install.sh` 以独立前缀安装。
- `gpu-run doctor`、`run-gpu --headless probe` 和 `gpu-run ahb` 报告 `AHB_ALLOCATE_SEND_RECEIVE_READBACK_RELEASE_OK`，`probe-present --motion` 已通过；探针识别 `Mali-G925-Immortalis` 并报告 `VULKAN_DEVICE_SUBMIT_READBACK_OK`、`VULKAN_SWAPCHAIN_RECREATE_PRESENT_OK`。
- 已通过 `scripts/activate-release.py` 原子切换 `/usr/local/bin/{gpu-run,gpu-launcher,run-gpu,gpu-env}`，同步 Termux 启动脚本，备份在 `/opt/cc-switch-update-helper/backups/r3.6-activation-20261125/`。X11 重启后 XFCE 已恢复。CC Switch PID 28773 已经通过统一入口重新启动，maps 中可见 r3.6 sysvk/libhybris/WSI、Mali 与 Mesa EGL；短时启动日志报告主窗口已显示。Zink 对缺少两个基础 feature 有警告，尚未完成长时闪烁/透明度验收。
- Termux:X11 最新锁定 0015–0017 的 rc1 APK 已安装，前端/server PID 21872/21829 均映射 APK `b5f92532…`（inode 2803251）。安装前旧 APK `5aed7953…` 已备份至 `/opt/cc-switch-update-helper/backups/r3.6-x11-apk-20261125/installed-before.apk`。
- 详细实现路线、透明度处理边界和新 chroot 复现步骤见 [r3.6 实现路线](r3.6-implementation-plan.md)；构建证据见 `evidence/r3.6-linux-candidate-20261125.json`；激活、安装、当前映射证据见 `evidence/r3.6-deployment-20261125.json`。

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
