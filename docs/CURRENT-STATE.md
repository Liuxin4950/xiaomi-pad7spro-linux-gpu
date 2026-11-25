# 当前状态（2026-11-25）

**生产 Linux 渲染栈仍为 r3.5；X11 已部署 r3.6 鼠标输入候选。2026-11-25 已完成独立 Linux r3.6 候选构建与硬件探针验证，但尚未切换生产入口，正式版验收仍未完成。** 快速蓝牙鼠标仍有用户报告的跳动，不能把候选改名 final 当作修复。

## 唯一运行身份

| 对象 | 当前值 |
|---|---|
| 设备 | Xiaomi Pad 7S Pro / 25053RP5CC |
| 本次回读系统 | Android 17 / API 37 / OS4.0.5.0.XOTCNXM |
| Linux 前缀 | `/opt/pad7spro-gpu-fps-20261017`；`release.json` 仍为 r3.5 |
| 统一入口 | `/usr/local/bin/gpu-run`、`gpu-launcher` |
| WSI SHA-256 | `d011bb7b220ab83bfb7c136e1e1b3190def27c013cb24775167c405073d77636` |
| 已安装 X11 / 前端映射 | `1.03.01-d55f1b7-gpu-r3.6-cursor-input-candidate`；APK `5aed79535688e4abb65eeb485de65fe2fdebe243911b98123b4d06e94b93996d` |
| 独立 X server 映射 | 空 state 修复包 `cdee031cdd778bc6f92c3c1f7cf45506db6801fd5ecc1fe3540b1fb4e519f223`；没有随前端热更新 |
| 本轮新构建 | `1.03.01-d55f1b7-gpu-r3.6-rc1`；未安装，完整哈希见发布证据 |
| 显示与输入 | 原生分辨率，上限 120；相对捕获临时为 true，效果未验收 |

PID 必须现场重取。本轮只同步启动文件，没有替换 APK、停止桌面或重启服务；启动逻辑在下次正常启动采用。

## 2026-11-25 Linux r3.6 候选

- 新候选前缀：`/opt/pad7spro-gpu-r36-20261125`；构建目录：`build/r3.6-linux-20261125/`。由锁定源码在 aarch64 fresh build，使用 `scripts/install.sh` 以独立前缀安装。
- `gpu-run doctor`、`run-gpu --headless probe` 和 `gpu-run ahb` 报告 `AHB_ALLOCATE_SEND_RECEIVE_READBACK_RELEASE_OK`，`probe-present --motion` 已通过；探针识别 `Mali-G925-Immortalis` 并报告 `VULKAN_DEVICE_SUBMIT_READBACK_OK`、`VULKAN_SWAPCHAIN_RECREATE_PRESENT_OK`。
- 没有改 `/usr/local/bin` 生产链接、没有重启桌面、没有替换 X11 APK。当前生产仍是 `/opt/pad7spro-gpu-fps-20261017` 的 r3.5。
- 详细实现路线、透明度处理边界和新 chroot 复现步骤见 [r3.6 实现路线](r3.6-implementation-plan.md)；证据见 `evidence/r3.6-linux-candidate-20261125.json`。

## 2026-11-25 通用入口补充

- 当前前缀增加 `bin/run-gpu` 与 `bin/gpu-env`，并建立 `/usr/local/bin/run-gpu`、`gpu-env` 链接；备份在 `/opt/cc-switch-update-helper/backups/gpu-common-env-20261125/`。`run-gpu 应用 参数` 默认使用 auto 硬件路由；`source /usr/local/bin/gpu-env` 导出共用 Vulkan/Zink/Mali 环境。
- 新 chroot 可使用 `scripts/install-global-env.sh` 安装 Bash 登录 profile hook；默认仅预览，写入时必须指定新备份目录。
- 当前 XFCE 会话早已从 `gpu-run gl ... startxfce4` 继承 r3.5 Vulkan/Zink/Mali 环境，本次没有重启会话。`gpu-env` 把同一套公共变量显式化，供新 chroot 的桌面会话和登录 shell 复用；WebKit preload 与 Electron 参数仍按应用单独处理。
- 这属于 r3.5 前缀的入口/环境补充，不代表 Linux GPU 库升级为 r3.6，也不证明所有应用后端都已硬件加速。普通 Vulkan/Zink 客户端可直接继承会话环境；需专用启动参数或本身使用 CPU 绘制的应用仍需适配与实测。

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
