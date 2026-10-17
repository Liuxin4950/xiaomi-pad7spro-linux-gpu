# 平板 / 后续 AI 接手

2026-10-17 会话保护更新：继续优化期间两次 APK 安装均伴随当前会话中断，用户已明确要求先通知、由其安排重启 Termux。后续完成候选构建、验证和备份后协调切换，不再自动安装 APK/重启服务端。当前在测包已为 `9c6276b8…`，实际映射与验收以新增证据为准；下方 `c62abdc5…` 为上一轮已验收基线。

2026-10-17 当前在测包 `9c6276b8…` 已在两端加载，包含新的 tick 许可时机修复和最终绘制合并；无追踪提交约 119/s、SF 内容层短快照 117.18/s、712704 像素零差异。持续独立页面内容 120 帧目标仍未完成，见 [本轮证据](../evidence/display-permit-surface-submit-2026-10-17.json)。

新候选 **88346b58… 尚未安装**：`build/x11-copy-wake-20261017/candidate.apk`，含 0014 的 tick 内 enqueue 通知延后，复用原有许可、队列和 fence。旧包原件为 `build/copy-wake-20261017/rollback/current.apk`，已核对 `9c6276b8…`。生产函数 UBSan 回归、提前唤醒/先唤醒后开许可/删除 CPU 必要唤醒三个负向对照、正式构建及包校验通过。没有新实机收益结论；先由用户保存工作并安排切换，再安装，由用户重启 Termux，之后重取 PID、核对两端 APK SHA、定向复核合并拷贝/实际提交与遮挡像素。不要自动安装，也不要运行 zink 或停止脚本。[完整候选证据](../evidence/deferred-copy-wake-2026-10-17.json)。

切换后的单次诊断已准备：`python3 build/copy-wake-20261017/acceptance/capture.py`。它先重取 PID/start ticks 并核对两端 APK 均为 `88346b58…`，再创建独立窗口和追踪；已验证旧包会在任何窗口/追踪启动前被拒绝。诊断沿用旧样本显式的 `NoCompositorFrameAcks:pending_frames/2`，不改变默认启动器；日常无追踪样本仍另测。结束后自动用已有埋点关联 WSI pixmap/serial → GPU copy serial → Surface frame ID → `EGL_DISPLAY_PRESENT_TIME_ANDROID`，过滤重复来源、未完成时间戳和未匹配帧。旧诊断样本约 4.89 秒内得到 530 个新 WSI 来源的已呈现帧，约 108.14/s；带采样，不能当日常帧率，也不能代替逐帧像素比较。脚本、结果与哈希见候选证据的 `prepared_acceptance`。

页面节拍后续核对：原生 Vulkan / ANGLE 同会话对比未支持切换默认；optimal AHB 候选没有页面速率收益，未登记为生产补丁，独立实验前缀已清理。不要加入 `--disable-frame-rate-limit`：已测到 630–902 rAF/s 和约 4.6 核浏览器 CPU 开销，不能代表屏幕内容更新。Chromium 的 `Swap throttled` 是队列状态，不是掉帧计数；原生 Vulkan 输出后端固定一次交换在途，WSI 已有四缓冲、两次显示提交上限，不要据此盲目扩大队列。接下来用已有 frame-sequence / Scheduler 追踪定位未更新帧的主线程准备与显示等待，详见同一证据的 `pacing_review`。本轮未安装 APK、未重启会话。

2026-10-17 前一轮已验收基线：默认链接已切到 `/opt/pad7spro-gpu-fps-20261017`，APK `c62abdc5…` 已在 server / renderer 两端加载。联合验收：3000 帧 FIFO 116.84 次提交/秒，默认入口复测 119.31/s；Chromium 119.45 rAF/s、缩放后 115.11，Mali / GaneshVulkan / ANGLE 和 WebGL / 0 崩溃通过；SF 内容层快照 111.95 次呈现/秒。712704 个物理像素零差异，包含 25 矩形遮挡、增量和空列表；oldSwapchain/缩放/Flip 通过。详细 source/build/hash、早前 800 像素失败及修复、回退见 [交付证据](../evidence/fps120-release-2026-10-17.json)。

用户已正常重开助手；新 GPU 进程 PID 22446（start_ticks 44231138）已确认加载新前缀 WSI、sysvk 和原厂 Mali，最后一项生效检查通过。**不要为此停止桌面、不要运行 zink 脚本、不要直接杀当前对话客户端。** 新启动应用已走修复版；旧前缀、APK 和激活备份均保留。功耗、精确输入延迟、长期稳定性及每帧屏幕独立内容率未测。下文为历史阶段快照。

2026-10-17 配套资源已同步：五份 Termux 会话脚本与设备一致，版本、Widget 入口、安装/重开/映射边界及回退流程见 [reference](../reference/README.md)。共享 shell/stop 现由 activate-release 一并备份迁移；未执行启动或停止。后续优化继续以当前修复版为基线。

2026-10-17（0010 已安装，服务端待切换）：0009 两端映射已实际切到 `88ce7f61…`，完整无追踪 600 帧约 81.98 次提交/秒、P95 20.87 ms；822 个 GPU Present 中有 240 个 25 矩形任务成功分两项，未采到回退或 pixman 拷贝热点。剩余 CPU 热点已由调用链确认是根缓冲在 lorieRedraw 中反复 AHB CPU lock/unlock。0010 改为实际 CPU 访问时才映射，CPU 写入刷新后才释放 GPU 锁，不改共享 ABI 或 GPU fence。干净构建、扩展生产函数回归/错误刷新顺序负向对照及包校验通过，已直接安装/打开 `804ecfc9…`；未运行 zink、未停桌面，服务端仍是 `88ce7f61…`。用户保存工作后的重启正在协调，随后必须完成帧率/回退缓存采样和物理像素/遮挡验收；目标未完成。证据与本机验收命令见 [根缓冲 CPU 访问](../evidence/scoped-root-cpu-access-2026-10-17.json)。

2026-10-17（0009 已安装，服务端待重启）：精确裁剪的原子分批候选 `88ce7f61…` 已构建、主机回归及包校验通过，并直接安装/打开 Activity；未运行 zink、未停桌面。0009 撤掉 0008 的放宽，将 25 块拆成两项共用一个 serial/fence，布局不变，保留遮挡洞。当前服务端仍是旧 `7f13f30e…`，待用户保存工作后重启，目标仍未完成；之后必须用新版映射、无追踪帧率、独立回退/CPU 采样及像素/遮挡证明实际效果。见 [分批候选证据](../evidence/present-copy-chunks-2026-10-17.json)。

2026-10-17（用户重启后）：两端 APK 映射已确认都是新 `7f13f30e…`，X server PID 28829、Android renderer PID 852，120 配置和 Mali 正常。**性能验收失败**：完整无追踪 600 帧小窗口约 43.73 次提交/秒，帧间隔 P95 38.04 ms；另一个 3000 帧任务在 65 秒超时，保留中断数据。独立诊断抓到 214 次 `CopyFallback.4.25.0`，pixman 占 X server CPU 周期样本 81.65%。最终 25 块仍超出单项 16 块限制，0008 的完整可见源放宽不足以消除本场景回退。下一步要支持更多可见矩形，保留弹窗/IME 的 clip 洞和 fence/所有权语义；不以未裁剪包围盒代替。未再次重启/运行 zink，追踪已关闭。详见 [重启后证据](../evidence/present-fragmented-post-restart-2026-10-17.json)。

2026-10-17（直接安装后历史快照，已由上方重启后状态取代）：用户要求直接覆盖安装候选 APK 后打开 Termux:X11，不运行 zink 脚本；已执行成功，未停止桌面。已安装与 Android renderer 映射哈希为 `7f13f30e…`，但独立 X server 保留旧 PID/starttime，已删除映射对应 APK 实测哈希仍为 `e5aa6b77…`。**0008 的服务端 Present 修复尚未生效**，直接打开 Activity 不会热换 X server。保持当前会话；后续经安排重启 X server，再核对新映射并做验收。见 [直接安装证据](../evidence/present-fragmented-install-2026-10-17.json)。

2026-10-17（构建完成时快照，后续见上）：0008 碎片化 Present damage 候选已构建并完成静态包校验，当时尚未安装；线上仍是 r3.5 可复现 APK，前缀/链接未改。候选及旧 APK 回退文件、SHA-256、构建封装修复与验收边界见 [候选证据](../evidence/present-fragmented-candidate-2026-10-17.json) 和 [CURRENT-STATE](CURRENT-STATE.md)。不得把构建通过当作卡顿已修复；具体回退原因仍待 CopyFallback 埋点确认。完整可见区本身也可能超过 16 块。停桌面会结束承载当前对话的客户端，仍须用户保存全部工作并明确授权。

2026-10-16：统一 gpu-run、Termux 桌面入口及 profile-display 默认值已同步为 **120 FPS**。用户正常重开后，已确认 X11 `-max-fps 120`、根属性 `[1,120,15]` 与 SF 图层周期 8.333 ms；原“当前仍为 60”属于重开前快照。Android 实际显示模式约 120 Hz，保留系统动态降频能力。配置上限不等于 120 张新内容/秒：无额外采样工具时 3000 帧小窗口探针平均约 80.1 fps，仍有周期性停顿。见 [运行诊断](../evidence/fps120-runtime-diagnosis-2026-10-16.json)。

2026-10-15：当前为 r3.5 可复现构建版，默认前缀 `/opt/pad7spro-gpu-r3.5-repro-20261015` 与新 arm64 APK 已实际加载，核心验收通过；最新哈希/范围见 [CURRENT-STATE](CURRENT-STATE.md) 和 [实施证据](../evidence/optimization-2026-10-15.json)。用户明确不要测试时结束承载当前对话的桌面；不再主动停止该 chroot 会话，使用独立进程和窗口继续。下文 r3.5 原前缀与 APK 为历史/回退信息。

更新：2026-10-13。用户明确要求全域替换：r3.5 APK 已安装、gpu-run/gpu-launcher 已切换、桌面已正常重开；实际新 APK 和桥接映射见 [全域替换证据](../evidence/r3.5-global-switch-2026-10-13.json)。Termux 三种启动入口继续追随统一 gpu-run，Mali / GaneshVulkan / ANGLE Vulkan / Zink 保留。下方 r3.4.1 和失败记录为历史，不代表当前运行版本。功耗、精确输入延迟和长期稳定性仍未确认。

更新：2026-10-13。当前默认 r3.5，先读 [CURRENT-STATE](CURRENT-STATE.md)。旧 r2、早期 canary 和历史实验数字不能作为当前启动配置。

## 设备入口

工作区 `/opt/pad7spro-gpu-release-test/repository`，别名 `/root/Working/xiaomi-pad7spro-linux-gpu`。容器为 Debian 13，Android rootfs 路径 `/data/linux/debian`；用户可能称其 Ubuntu，不据此另找第二个 rootfs。

- 当前默认前缀 `/opt/pad7spro-gpu-fps-20261017`，系统 gpu-run/gpu-launcher 链接到这里，版本与文件状态读 release.json / install-manifest.json。r3.4 原件保留在 `/opt/pad7spro-gpu-next`，存在 damage 语义和缓冲轮换错误，禁止再选作默认。初版修复保留于 `/opt/pad7spro-gpu-r3.4.1`，稳定回退 r3.3 保留于 `/opt/pad7spro-gpu-observe-20261012`。优化版已完成窗口/像素/Chromium/Trae 定向验收，用户已重开，当前桌面/助手 GPU 实际映射 r3.5；以 CURRENT-STATE 为准。
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
