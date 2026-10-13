# 平板 / 后续 AI 接手

更新：2026-10-13。当前默认已回退 r3.4.1，先读 [CURRENT-STATE](CURRENT-STATE.md)。旧 r2、早期 canary 和历史实验数字不能作为当前启动配置。

## 设备入口

工作区 `/opt/pad7spro-gpu-release-test/repository`，别名 `/root/Working/xiaomi-pad7spro-linux-gpu`。容器为 Debian 13，Android rootfs 路径 `/data/linux/debian`；用户可能称其 Ubuntu，不据此另找第二个 rootfs。

- 当前默认前缀 `/opt/pad7spro-gpu-r3.4.1-opt1`，系统 gpu-run/gpu-launcher 链接到这里，版本与文件状态读 release.json / install-manifest.json。r3.4 原件保留在 `/opt/pad7spro-gpu-next`，存在 damage 语义和缓冲轮换错误，禁止再选作默认。初版修复保留于 `/opt/pad7spro-gpu-r3.4.1`，稳定回退 r3.3 保留于 `/opt/pad7spro-gpu-observe-20261012`。优化版已完成窗口/像素/Chromium/Trae 定向验收，用户已重开，桌面/助手 GPU 实际映射 r3.4.1；以 CURRENT-STATE 为准。
- Termux Widget、`~/debian-desktop.sh` 和 `~/mali-work/desktop-zink.sh` 共用 GPU 桌面入口。普通桌面不再默认 llvmpipe。
- 桌面、菜单、URL、XFCE helper 和 CLI chromium/chatgpt/ChatGPT/trae/trae-cn/cc-switch 全部统一到 gpu-run。Office 图标也进入同一环境；MySQL、shell/TUI 不强加图形参数。
- 二维 Skia 原生 Vulkan；WebGL ANGLE Vulkan；GL Zink；CC Switch 使用 WebKit 适配。
- 原生分辨率，60 fps 请求与 WSI 上限；BGRA 字节契约，不设置 vblank_mode=0，不自动软件回退。

## Android 实际文件同步

三个设备文件已经更新，最终 SHA-256 与仓库参考文件逐字节一致；原件保留在 `build/entry-handoff-20261012`。

| Android 文件（Termux home 下） | 仓库参考文件 |
|---|---|
| `mali-work/desktop-zink.sh` | `reference/termux/desktop-zink.sh` |
| `debian-desktop.sh` | `reference/termux/debian-desktop.sh` |
| `.shortcuts/debian-zink.sh` | `reference/termux/debian-zink-widget.sh` |

Termux home 是 Android `/data/data/com.termux/files/home`；在本 chroot 用 `/proc/1/root` 前缀访问。更新入口必须同步这里的实际文件；仅改 chroot bin 或仓库参考文件不算交付。设备文件属主与组 10305、权限 0700，原标签保留。已有 shell/TUI、停止脚本和用户数据保持原用途。完整哈希和核对时间见 `evidence/entrypoints-2026-10-12.json`。

## 安全接手步骤

```sh
cd /opt/pad7spro-gpu-release-test/repository
git status --short
readlink -f /usr/local/bin/gpu-run
gpu-run doctor
gpu-run info GPU_PID
```

查当前实际进程，不抄历史 PID。doctor / 命令行参数只证明前置配置；renderer、Skia 后端和已显示窗口才是运行证据。源码修改不自动更新安装前缀；manifest / 入口 / 文档需同步。 更新启动器时必须保留可执行权限（安装目标 gpu-run 为 0755），并执行 `test -x /usr/local/bin/gpu-run` 和真实菜单可见性核对；文件内容哈希、desktop-file-validate 和 stub 检查不能代替这项检查。RUNPATH 固定，不能随意重命名前缀。

已安装 gpu-direct APK（详细版本/哈希在 CURRENT-STATE）。r3.4.1 修复不改 APK。每次核对当前 X server 与应用映射，不能沿用历史“已重开”的结论。最终核对快照见 entrypoints 证据；快照 PID 不能照抄用于以后的诊断。以后升级仍需区分文件更新与已运行进程；再次点已有单实例只复用它。正常停止桌面会结束 chroot 应用，先保存工作，不直接全局 pkill。

## 回退和诊断

单应用硬件回退：`PAD_GPU_SKIA_BACKEND=angle gpu-run chromium`。显式 CPU 参考：`gpu-run --software chromium`。完整 r3.3 保留为稳定回退目录，统一链接切回后重开应用；不覆盖在用库。

Android 核心探针现在默认跟随 rootfs 中的 gpu-run 系统链接：

```sh
su -W -c '/system/bin/sh /data/linux/debian/opt/pad7spro-gpu-release-test/repository/scripts/android-probe.sh'
```

私有运行证据/入口备份在 build，公开脱敏证据在 evidence。不要提交 APK、测试 profile、系统 DB、厂商库或私人日志。不修改系统分区/SELinux，不直接禁用系统服务。不要执行旧 disable-miui-telemetry.sh。

WSI、rAF、SF 呈现与屏幕实际新帧分开；短时电流不证明长期续航。MiuiDaemon 一条坏记录已备份隔离；搜狗忙循环已定位到 CursorAnchorInfo/Hook 路径，模块设置未改。后续若复发先抓同 PID / starttime 与真实 CPU，不要继续盲改 Vulkan。

入口与文档最新变更记录见 `evidence/entrypoints-2026-10-12.json`，渲染证据见 `evidence/r3.3-native-rendering-2026-10-12.json`，r3.4 damage 拷贝证据见 `evidence/r3.4-damage-aware-copy-2026-10-13.json`。历史实测保留，不重写成新版成绩。

最新优化、真实应用增量提示与屏幕检查见 `evidence/r3.4.1-optimization-2026-10-13.json`。复制像素减少不是整机功耗测量。

显示效率候选 r3.4.2 已独立保存在 `/opt/pad7spro-gpu-r3.4.2-display`；对应 APK、当前 APK 原件和签名/对齐核对在私有 `build/r3.4.2-display-20261013`。APK 未安装，系统链接未变，保存会话前不得替用户停桌面。候选默认 auto 需要新 X server 的能力协商，旧 APK 自动保留 timer。技术交付与部署步骤见 [r3.4 显示链路](r3.4-display-efficiency.md)。

部署后运行状态已更新至 [整链路结果](r3.4-display-results.md)。本页“未安装/未重启”表述属于候选构建完成时的历史快照；实际是否保留新 APK 或自动回退，以结果中的实装哈希为准。默认桥接未自动推广。

最新用户重启后核对：统一入口及 Zink/Widget 三个脚本已生效于 r3.4.1；r3.4.2 部署在原 APK 基线准备阶段失败，新 APK 从未安装。后台 worker 的 chroot 调用已修正为先加入正常桌面的挂载命名空间，前置 doctor 通过；完整 A/B 仍未完成，旧失败记录保留。

本次按用户明确要求已安装 r3.4.2 APK 并切换统一入口；新进程检查将使用已修正的桌面挂载命名空间。具体完成/回退状态看 [升级结果](r3.4-upgrade-results.md)。

本次用户明确要求安装并更新到 r3.4.2。部署结果：`upgrade_verification_failed`；实际默认前缀 `/opt/pad7spro-gpu-r3.4.1-opt1`。前文候选未安装、旧 PID 等属于历史快照；当前以 [升级结果](r3.4-upgrade-results.md) 为准。没有新增功耗/真实输入延迟改善结论。

最新核对：r3.4.2 APK 与入口均因窗口验收未通过而回退至原 APK / r3.4.1。稳定版本同样触发前后台恢复像素检测差异，检测需处理 viewport；候选 Copy 目标 MSC 的 +2 依据也已确认错误。先修正这两处再重新验收，不能绕过检测直接切回候选。
