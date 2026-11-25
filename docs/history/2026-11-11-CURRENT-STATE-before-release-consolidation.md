# 当前部署：r3.5 Linux 栈 + r3.6 光标等待修复候选

2026-11-11 后续输入排查：第二包用户反馈与第一包无区别，未验收。已用现有偏好临时启用 `pointerCapture=true`，系统确认 `RELATIVE` 模式；60秒实际移动和完整12秒跟踪已取得，不能把回调约100次/秒当作物理120FPS。相对模式效果仍未获用户明确认可，若无益可通过既有偏好广播恢复false；完整偏好原件私有备份保留。当前没有再次换包，详情见 [r3.6 研发记录](r3.6-development.md)。

2026-11-11 当前最新候选：第一轮鼠标等待修复经用户反馈“有一定改善，但快速移动仍瞬移”，**未验收通过**。同一轮已授权切换验证中追加 Android 鼠标源无缓冲分发，现安装 `1.03.01-d55f1b7-gpu-r3.6-cursor-input-candidate`，APK SHA-256 `5aed79535688e4abb65eeb485de65fe2fdebe243911b98123b4d06e94b93996d`；前端实际映射已核对，server/XFCE 会话保持原启动代次。第二包安装后曾显示 Not connected，直接确认 UID 10305 被 Greezer 冻结；正常切换 Termux→X11 后恢复。Widget 的 PowerKeeper 配置再次回到 miuiAuto，已只恢复该应用 noRestrict，派生名单和 Greezer `fgservice|NO_RESTRICT_APP` 已回读。第二候选用户反馈“和第一版本没有区别”，快速鼠标问题仍未解决；长期防冻结也仍待验证，不能宣称 120 FPS 或 r3.6 定版。详见 [当前鼠标修复证据](../evidence/r3.6-cursor-independent-wake-2026-11-11.json)。

2026-11-11 鼠标卡顿跟进：用户报告蓝牙鼠标闪烁、延迟及短距离跳动，Scene 浮窗约 11–50。已确认独立光标处理仍被主帧等待条件限制，候选将光标更新提前至该等待之前，同时在同次迭代继续处理桌面/拷贝工作。用户回复“已保存，可以切换验证”后安装 `1.03.01-d55f1b7-gpu-r3.6-cursor-wake-candidate`，完整 APK SHA-256 为 `2cba32a872d3d290bef0566d6838398eae7ab6b397fc884fdbe3e025678511fb`。新前端实际映射已确认；独立 X server 仍加载前一个空 state 修复包，XFCE 会话未重启。**当前等待真实蓝牙移动验收，尚不能声称跳动已消除或达到 120 FPS。** 证据见 [光标等待修复记录](../evidence/r3.6-cursor-independent-wake-2026-11-11.json)。以下为空 state 修复包及历史记录。

2026-11-11：已安装 `1.03.01-d55f1b7-gpu-r3.6-final-20261111` 的空 state 修复包，完整 APK SHA-256 为 `cdee031cdd778bc6f92c3c1f7cf45506db6801fd5ecc1fe3540b1fb4e519f223`。当前被动核对确认 Android 前端和独立 X server **均映射该包**；XFCE 与 Fcitx5 正在运行。Linux 前缀/WSI 保持 r3.5。此核对没有安装、启动或重启会话。

此前 final 包（`ba9310e3…`）存在 Surface 到达早于共享 state 的必现空指针崩溃，已由最小空值检查修复并通过前端冷启动验证；新增生产函数回归覆盖无 state、残留渲染目标及无渲染目标三种条件。**包名中的 final 不代表所有验收完成**：旧候选的光标实机结果不能直接代替修复包复验，整会话冷启动也尚无完整验收证据。见 [修复与研发记录](r3.6-development.md)、[故障修复证据](../evidence/r3.6-cursor-null-fix-2026-11-11.json) 和 [当前实际映射核对](../evidence/r3.6-fixed-current-2026-11-11.json)。以下 r3.5 数据与旧候选进展均保留为历史记录。

2026-10-17：用户明确以当前结果作为 **r3.5 最终版本**，发行标识 `r3.5-final-20261017`。本轮优化已收尾；未达到稳定真实 120 帧、长期功耗/输入延迟等项目作为已知限制保留，不再自动执行旧计划或更换 APK。

| 项目 | 定版值 |
|---|---|
| 发行版 / 标识 | r3.5 / `r3.5-final-20261017` |
| 已部署 Linux 前缀 | `/opt/pad7spro-gpu-fps-20261017`（保留既有 RUNPATH，不改目录名） |
| 统一入口 | `/usr/local/bin/gpu-run`、`gpu-launcher` 指向上述前缀 |
| 当前已安装 X11 鼠标输入候选 APK SHA-256 | `5aed79535688e4abb65eeb485de65fe2fdebe243911b98123b4d06e94b93996d` |
| WSI 库 SHA-256 | `d011bb7b220ab83bfb7c136e1e1b3190def27c013cb24775167c405073d77636` |
| 默认渲染 | Skia 原生 Vulkan；WebGL ANGLE Vulkan；GL Zink；原厂 Mali-G925 |
| 默认显示配置 | 原生分辨率；X11 / WSI 上限 120；BGRA；诊断默认关闭 |
| 已纳入补丁 | r3.5 锁定补丁 + 独立光标候选移植；Linux WSI 仍至 0012，候选顺序与构建报告见 r3.6 记录 |

历史 r3.5 Android versionName 为 `1.03.01-d55f1b7-gpu-r3.5-repro`；历史光标候选为 `1.03.01-d55f1b7-gpu-r3.6-cursor-candidate`，当前修复包为 `1.03.01-d55f1b7-gpu-r3.6-final-20261111`，以完整 APK 哈希和各进程映射分别识别。

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

## OS4 / Android 17 运行环境补丁（2026-11-06）

设备已升 OS4（Android 17，内核 6.18.21-android17），GPU 栈 r3.5 内容未变；应用两处内核回归补丁，均为文件级、重启后保持：
1. mount/umount2/chroot 被 app seccomp 拦截（SIGSYS）→ chroot 特权操作统一经 `~/debian-root.sh`（adb shell `Seccomp:0` + nsenter；`~/debian-shell.sh` 自动 source，全部 launcher/Widget 入口不变）。
2. 无 caps 的 root 进程 clone3 必 EAGAIN（Chromium/Electron 子进程 capset 清零触发崩溃循环）→ `/usr/local/lib/libkeepcaps.so` LD_PRELOAD shim + chroot `/etc/ld.so.preload` 全局预载；**回滚=删除该 preload 文件**。
详见 `/data/linux/debian/root/Working/GPU-CURRENT.md` 的 OS4 节（chroot 内路径 `/root/Working/GPU-CURRENT.md`）。ChatGPT TLS `ERR_CONNECTION_CLOSED` 为 Cloudflare/代理出口问题，与本栈无关。

## OS4 稳定性修复（2026-11-10）

实际故障捕获到 Greezer `ABNORMAL_MODE` 冻结 Termux 父 UID cgroup，不能继续仅按 idle/Choreographer 猜测。上午只补 Settings 派生名单的改动在 14:55 复发时已丢失，修补不完整；下午改为 PowerKeeper ContentProvider 中 Widget 的原始 `bgControl=noRestrict`，系统自行同步名单并识别 `NO_RESTRICT_APP`。未更换 GPU/APK、未重启。会话脚本另修复 ADB 观察失败误清理风险，已备份原子落盘，**下次正常启动才生效**。59 项单测通过；锁屏/夜间/长期稳定性及透明黑块仍未验收。完整证据、回退与维护边界见 [OS4 稳定性记录](os4-stability-2026-11-10.md)。

## 新一轮适配候选（2026-11-10）

用户重新提出改善 GPU 与平板融合、能效和流畅度。已定位 Writer Skia 临时上下文窗口 0 的 Present 注册失败链，并构建隔离 WSI surface-loss 防御候选，通过 mock 和真实 Mali 窗口/resize 探针；未部署、未换 APK 或重启，也未声称 Writer 硬件适配或性能改善已完成。见 [本轮候选与验证](gpu-integration-2026-11-10.md)。

## 历史记录：r3.6 研发启动时状态

新目标为有实质性能、适配、能效或功能更新的 r3.6。独立 SurfaceControl 光标候选 APK 已完成全新构建、签名/对齐、原裁剪/ownership/frame gate 回归及新增光标快照测试，当前未安装；实际效果待用户安排安全切换后验收。Writer 的 Skia Vulkan 中文窗口和翻页已在独立进程跑通，但关闭时仍崩溃，不能推广。研发路线、产物、哈希、备份和验收缺口见 [r3.6 研发记录](r3.6-development.md)。


## 历史候选：2026-11-11 光标实机验收进展

已在当前部署验证纯光标移动/换形/隐藏不增加主 Surface 整帧绘制：约 2 秒发出 225 次移动指令，内部 renderer 新增绘制 0；物理截图核对 24×24 / 48×16 形状、热点、位置及隐藏均正确。经 WindowManager 确认的 Termux/X11 前后台切换和 surface 不可用后恢复也通过。不是物理 FPS、输入延迟或整机功耗结论。详细范围、失败样本和未验收项见 [r3.6 研发记录](r3.6-development.md)，公共摘要见 [光标运行证据](../evidence/r3.6-cursor-runtime-2026-11-11.json)。r3.6 尚未定版。


## 2026-11-11 Clipman 重复启动弹窗修复

实机发现两个不同 XDG ID 都执行 `xfce4-clipman`：用户 `xfce4-clipman.desktop` 与系统同名覆盖 `xfce4-clipman-plugin-autostart.desktop`。两者同秒由 XFCE 启动。D-Bus `org.xfce.clipman` 的实际持有者为正常进程 12758，报错窗口 `_NET_WM_PID=12756` 属另一进程；不能把截图中的 Clipman 弹窗当成 Fcitx5 问题。xfsettingsd 另有内置剪贴板持久化选择权，但本次证据直接定位到 Clipman 的重复进程，未改 xfsettingsd。

修复用户启动项：重复的 `xfce4-clipman.desktop` 设置 `Hidden=true`；保留的系统同名覆盖在启动前查询 `org.xfce.clipman` 是否已注册，已有实例则静默返回。同步参考文件 `reference/chroot/xfce4-clipman*.desktop`。备份、前后哈希与回执位于 `build/clipman-autostart-20261111/`；恢复两份原件即可回退。

实际连续执行保留入口三次，均退出 0、无输出、没有新进程；三分支 stub 检查已有实例跳过、无实例启动及总线查询失败尝试启动均通过。只向 PID 12756 的错误窗口发送 WM_DELETE_WINDOW 关闭请求，正常 Clipman PID 12758 与其启动代次、D-Bus 身份保持不变；未重启桌面、未修改剪贴板内容或删除历史。未以整桌面重启复测作为已完成结果。
