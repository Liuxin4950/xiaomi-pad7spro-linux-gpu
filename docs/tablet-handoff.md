# 平板 / 后续 AI 接手

2026-10-17（用户重启后）：两端 APK 映射已确认都是新 `7f13f30e…`，X server PID 28829、Android renderer PID 852，120 配置和 Mali 正常。**性能验收失败**：完整无追踪 600 帧小窗口约 43.73 次提交/秒，帧间隔 P95 38.04 ms；另一个 3000 帧任务在 65 秒超时，保留中断数据。独立诊断抓到 214 次 `CopyFallback.4.25.0`，pixman 占 X server CPU 周期样本 81.65%。最终 25 块仍超出单项 16 块限制，0008 的完整可见源放宽不足以消除本场景回退。下一步要支持更多可见矩形，保留弹窗/IME 的 clip 洞和 fence/所有权语义；不以未裁剪包围盒代替。未再次重启/运行 zink，追踪已关闭。详见 [重启后证据](../evidence/present-fragmented-post-restart-2026-10-17.json)。

2026-10-17（直接安装后历史快照，已由上方重启后状态取代）：用户要求直接覆盖安装候选 APK 后打开 Termux:X11，不运行 zink 脚本；已执行成功，未停止桌面。已安装与 Android renderer 映射哈希为 `7f13f30e…`，但独立 X server 保留旧 PID/starttime，已删除映射对应 APK 实测哈希仍为 `e5aa6b77…`。**0008 的服务端 Present 修复尚未生效**，直接打开 Activity 不会热换 X server。保持当前会话；后续经安排重启 X server，再核对新映射并做验收。见 [直接安装证据](../evidence/present-fragmented-install-2026-10-17.json)。

2026-10-17（构建完成时快照，后续见上）：0008 碎片化 Present damage 候选已构建并完成静态包校验，当时尚未安装；线上仍是 r3.5 可复现 APK，前缀/链接未改。候选及旧 APK 回退文件、SHA-256、构建封装修复与验收边界见 [候选证据](../evidence/present-fragmented-candidate-2026-10-17.json) 和 [CURRENT-STATE](CURRENT-STATE.md)。不得把构建通过当作卡顿已修复；具体回退原因仍待 CopyFallback 埋点确认。完整可见区本身也可能超过 16 块。停桌面会结束承载当前对话的客户端，仍须用户保存全部工作并明确授权。

2026-10-16：统一 gpu-run、Termux 桌面入口及 profile-display 默认值已同步为 **120 FPS**。用户正常重开后，已确认 X11 `-max-fps 120`、根属性 `[1,120,15]` 与 SF 图层周期 8.333 ms；原“当前仍为 60”属于重开前快照。Android 实际显示模式约 120 Hz，保留系统动态降频能力。配置上限不等于 120 张新内容/秒：无额外采样工具时 3000 帧小窗口探针平均约 80.1 fps，仍有周期性停顿。见 [运行诊断](../evidence/fps120-runtime-diagnosis-2026-10-16.json)。

2026-10-15：当前为 r3.5 可复现构建版，默认前缀 `/opt/pad7spro-gpu-r3.5-repro-20261015` 与新 arm64 APK 已实际加载，核心验收通过；最新哈希/范围见 [CURRENT-STATE](CURRENT-STATE.md) 和 [实施证据](../evidence/optimization-2026-10-15.json)。用户明确不要测试时结束承载当前对话的桌面；不再主动停止该 chroot 会话，使用独立进程和窗口继续。下文 r3.5 原前缀与 APK 为历史/回退信息。

更新：2026-10-13。用户明确要求全域替换：r3.5 APK 已安装、gpu-run/gpu-launcher 已切换、桌面已正常重开；实际新 APK 和桥接映射见 [全域替换证据](../evidence/r3.5-global-switch-2026-10-13.json)。Termux 三种启动入口继续追随统一 gpu-run，Mali / GaneshVulkan / ANGLE Vulkan / Zink 保留。下方 r3.4.1 和失败记录为历史，不代表当前运行版本。功耗、精确输入延迟和长期稳定性仍未确认。

更新：2026-10-13。当前默认 r3.5，先读 [CURRENT-STATE](CURRENT-STATE.md)。旧 r2、早期 canary 和历史实验数字不能作为当前启动配置。

## 设备入口

工作区 `/opt/pad7spro-gpu-release-test/repository`，别名 `/root/Working/xiaomi-pad7spro-linux-gpu`。容器为 Debian 13，Android rootfs 路径 `/data/linux/debian`；用户可能称其 Ubuntu，不据此另找第二个 rootfs。

- 当前默认前缀 `/opt/pad7spro-gpu-r3.5-repro-20261015`，系统 gpu-run/gpu-launcher 链接到这里，版本与文件状态读 release.json / install-manifest.json。r3.4 原件保留在 `/opt/pad7spro-gpu-next`，存在 damage 语义和缓冲轮换错误，禁止再选作默认。初版修复保留于 `/opt/pad7spro-gpu-r3.4.1`，稳定回退 r3.3 保留于 `/opt/pad7spro-gpu-observe-20261012`。优化版已完成窗口/像素/Chromium/Trae 定向验收，用户已重开，当前桌面/助手 GPU 实际映射 r3.5；以 CURRENT-STATE 为准。
- Termux Widget、`~/debian-desktop.sh` 和 `~/mali-work/desktop-zink.sh` 共用 GPU 桌面入口。普通桌面不再默认 llvmpipe。
- 桌面、菜单、URL、XFCE helper 和 CLI chromium/chatgpt/ChatGPT/trae/trae-cn/cc-switch 全部统一到 gpu-run。Office 图标也进入同一环境；MySQL、shell/TUI 不强加图形参数。
- 二维 Skia 原生 Vulkan；WebGL ANGLE Vulkan；GL Zink；CC Switch 使用 WebKit 适配。
- 原生分辨率，新会话默认 120 fps 请求与 WSI 上限（2026-10-16；运行态已生效）；BGRA 字节契约，不设置 vblank_mode=0，不自动软件回退。

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

显示链路迭代最新为独立 r3.4.3 / r3.5，技术和交付范围见 [r3.5](r3.5-efficiency.md)。r3.4.2 和 r3.5 均曾安装，新版验收失败后恢复原 APK/r3.4.1；保留所有失败证据。r3.5 的窗口形状存在但颜色检测不通过，正在定向区分 Copy 与 Surface 阶段。关屏的离屏读回不作为实际显示验收；等待亮屏解锁后只做必要的颜色定位，再恢复稳定版本。旧“未安装”、旧 PID 和旧 MSC+2 说明都是历史快照。

全域切换前的历史收尾：r3.5 候选已核心验收、当时未全域替换，当前仍 r3.4.1/原 APK。用户明确额度不足、不要再反复重启；不要自动重跑 worker。继续前只读 [收尾证据](../evidence/r3.5-release-2026-10-13.json) 与 r3.5 文档，下一次正常切换须 APK/入口一起更新。无法确认项目已按用户要求跳过，不能宣称功耗、延迟和长期稳定性达标。
