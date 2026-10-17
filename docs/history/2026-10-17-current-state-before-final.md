> 历史快照：r3.5 最终定版前的逐轮记录；其中“当前/候选/下一步”仅对应当时阶段。最新定版见 [CURRENT-STATE](../CURRENT-STATE.md)。

# 当前运行基线：r3.5 FPS 修复版（2026-10-17）

2026-10-17 最新：用户授权安装并自行重启后，APK **`88346b5831c33e585d467bbf0f8255b972a05dca1ffb112a03bf683404625411` 已在 X server / renderer 两端实际加载**；Linux 前缀仍为 `/opt/pad7spro-gpu-fps-20261017`。0014 的通知时序改动生效：匹配浏览器拷贝中 standalone 从旧诊断 113/647（17.47%）降到 3/639（0.47%）；遮挡/增量/空区域共 **712704 个物理像素零差异**。无追踪 1200 帧探针约 **117.01 次提交/秒**，默认 Chromium 原生 Vulkan 页面约 **112.79 / 115.51 / 111.74 rAF/s**。显式 ACK 参数的 3000 帧试验约 119.79 rAF/s，但轻量 app-tags 追踪关联的新 WSI 来源已显示帧约 **105.52/s**，仍有采样影响；**尚未证实稳定真实页面 120 帧**，不把回调率当完成。没有更改默认 ACK 参数、Linux 库或驱动。当前安装清单和 release 元数据已同步，旧包可回退，见[切换与验收证据](../../evidence/deferred-copy-wake-2026-10-17.json)。不同阶段间桌面重启，不构成严格 A/B；没有新功耗或输入延迟结论。

以下 `9c6276b8…` 段落为上一轮快照；0014 准备时记录也保留历史语义。

2026-10-17 上一轮快照：当时 APK 为 `9c6276b8d3cce95709f8aba385ae5a2b1962cee30917d717e17478c671d60bac`，已核对 server / renderer 两端实际映射；Linux 前缀仍为 `/opt/pad7spro-gpu-fps-20261017`。新增 Termux 0012 在渲染开始前领取 tick 许可，避免 GPU 等待后覆盖新 tick；0013 先完成离屏拷贝，再合并根画面和光标为一次显式 flush，保留所有权栅栏。生产函数回归、负向对照和干净构建通过。两次 1200 帧客户端提交约 119.01 / 118.87 次/秒；独立 SF 内容层短快照约 **117.18 次呈现/秒**，P95 8.40 ms，最长 16.71 ms。遮挡/增量/空区域 **712704 个物理像素零差异**。不同阶段间桌面已重启，不能把 CPU/帧率差异当严格交替 A/B；**持续的独立页面内容 120 帧仍未证实，优化目标继续进行**。见 [本轮证据](../../evidence/display-permit-surface-submit-2026-10-17.json)。

**会话保护更新**：两次 APK 安装均伴随当前对话中断。用户已明确要求先通知、由其安排重启 Termux；后续先完成候选构建、验证和备份，不再自动替换 APK 或重启 X server。当前包已加载，这轮无需再重启。普通验证只使用独立窗口。

**页面节拍复核**：同会话原生 Vulkan → ANGLE Vulkan → 原生 Vulkan 对比未证明切换收益，ANGLE 出现 83–92 ms 长停顿。独立 optimal AHB 布局候选显示/遮挡像素通过，但页面速率未提高，未纳入生产补丁。`--disable-frame-rate-limit` 把 rAF 拉高到 630–902/s，并把浏览器相关 CPU 用量推到约 4.6 核，已拒绝；不能用回调空转冒充屏幕 120 帧。当前默认和 APK 保持，实验前缀已在进程退出后清理；详细追踪、CPU 范围及后续定位见同一份[本轮证据](../../evidence/display-permit-surface-submit-2026-10-17.json)的 `followup_review.pacing_review`。

**0014 切换前准备快照（现已安装并验收）**：0014 只延后 tick 内 GPU 队列通知，先开放已有绘制许可，再唤醒 renderer，减少 copy-only 和 root 各自一次 flush/fence 的机会；其他 enqueue 与 CPU 所有权等待仍可立即唤醒。独立浏览器诊断中，647 个匹配的 Present copy 有 113 个走了 standalone 路径。生产函数回归、三个负向对照、干净 arm64 构建、签名/CRC/16 KiB 对齐通过；候选 APK SHA-256 `88346b5831c33e585d467bbf0f8255b972a05dca1ffb112a03bf683404625411`，位置 `build/x11-copy-wake-20261017/candidate.apk`。旧 `9c6276b8…` 已备份，安装和 Linux 默认未改，须用户保存工作后协调 APK 切换与 Termux 重启。另测现有 `NoCompositorFrameAcks` 可使 rAF 接近 120，但实际 X11 请求仍约 115/s，未加到启动器。候选的实际收益、像素正确性与持续新内容率均待切换后验证，见[候选证据](../../evidence/deferred-copy-wake-2026-10-17.json)。

该轮准备的两端 APK 映射校验和单次诊断现已执行；旧包拒绝测试也已保留。已有埋点还可关联指定浏览器的新 WSI 来源帧与 EGL 报告的实际显示时间，比整层 SF 呈现计数更具体；它仍是有采样开销的来源关联，不是逐帧像素解码。命令、旧样本与当前结果见[交接](../tablet-handoff.md)及验收证据 `prepared_acceptance` / `post_restart_acceptance`；安装经用户明确授权，重启由用户完成。

## 前一轮已验收基线（以下 c62abdc5 与旧 PID 为历史快照）

默认 `gpu-run` / `gpu-launcher` 已切到 `/opt/pad7spro-gpu-fps-20261017`；Termux:X11 已安装且两端实际映射 APK `c62abdc50b9aca276a6f9e7956f8f099cbf39ee24b7abeea9ee3d3795f87c4b4`。原厂 Mali 保留，120 配置 `[1,120,15]` 正常。新栈完整 3000 帧 FIFO 探针 **116.84 次提交/秒**，默认入口复测 600 帧 **119.31/s**；隔离 Chromium **119.45 rAF/s**，缩放后 **115.11 rAF/s**，GaneshVulkan / ANGLE Vulkan / Mali、WebGL 回读和 GPU 崩溃计数 0 均确认。独立 SurfaceFlinger 内容层快照约 **111.95 次呈现/秒**；这些指标不等于逐帧屏幕新内容计数。

已修复：超过 16 块的可见区域 GPU 原子分批；纯 GPU 根缓冲不再反复 CPU 映射；CPU 弹窗绘制等待先前排队 GPU 所有权栅栏；WSI 最多两个有序 tick 在途，避免每帧串行等待。后者曾在 APK 804ecfc9 上暴露 800 像素遮挡覆盖，原失败证据保留；最新 APK 与新前缀联合检查 **712704 个物理像素零差异**，增量/空列表、窗口重建/oldSwapchain 和实际 Flip 路径通过。独立采样 1047 个 Present 没有 CopyFallback，WSI 在途数最多 2。

**应用重开后的生效检查已通过**：用户正常重开助手后，新 GPU 进程 PID 22446（start_ticks 44231138）实际映射 `/opt/pad7spro-gpu-fps-20261017` 中的 WSI、sysvk 桥接及原厂 Mali；此前旧进程快照保留在证据中。安装清单再次核验通过，本轮 FPS 修复验收已完成。本轮没有停止桌面、没有运行 zink 脚本；三份 Termux 入口文件保持原内容、UID/GID 和 0700。旧前缀、APK 和链接回退记录保留。功耗、精确输入延迟和长期稳定性未测。完整证据：[FPS 修复交付](../../evidence/fps120-release-2026-10-17.json)。

## Termux 配套资源（2026-10-17 同步）

已重新核对 Termux 0.118.3、Widget 0.15.0、Termux 侧 termux-x11-nightly 1.03.01-5 与补丁 APK `c62abdc5…`。五份主要入口与仓库逐字节一致，UID/GID 10305、0700；共享 shell / stop 也纳入带备份的入口迁移。文档中的旧前缀、60 FPS 和未安装候选说明已修正或明确标为历史。只显示已有桌面时直接打开 Termux:X11，具体生效边界与备份见 [配套资源](../../reference/README.md)和 [同步证据](../../evidence/termux-resources-2026-10-17.json)。本次未安装其他 Android APK，未执行桌面启动或停止脚本。

## 先前阶段记录（以下“尚未加载/未达标”均为当时快照）

2026-10-17（0009 实测与 0010 候选安装）：用户重启后，分批版 `88ce7f61…` 已在两端实际加载；完整无追踪 600 帧、640×480 探针 **81.98 次提交/秒，P95 20.87 ms**，X server CPU 282.34 ms/s。独立诊断中 822 个 Present 已卸载 GPU，其中 240 个 25 矩形 Present 各用两项；**没有 CopyFallback 事件，pixman 软件拷贝热点未再采到**。相较此前约 43.73/s 已有改善，但桌面负载不同，不是严格 A/B，尚未达到预期 110～120。带调用链的独立采样证明剩余热点在 `lorieRedraw` 的整屏 AHB CPU lock/unlock（children 73%，缓存清理/失效占 self 样本约 63%）。据此增加 0010：AHB 根缓冲发布后不立即重新 CPU 映射，真实 CPU 绘制仍按 EXA access 映射并在释放 GPU 锁前刷新；GPU flip 不新建 CPU 映射，保留 legacy FD 路径及 GPU 栅栏。生产函数 UBSan 回归、故意错误的刷新顺序负向对照、干净 arm64 构建与包校验通过。已直接安装/打开 `804ecfc9e0b068b1ef3a631c920f16f399d908b39b8d816b365afa0693debe39`，未停桌面、未运行 zink；**服务端仍是 `88ce7f61…`，0010 尚待用户保存工作后重启及实机验收，目标仍未完成**。见 [根缓冲 CPU 访问证据](../../evidence/scoped-root-cpu-access-2026-10-17.json)。

2026-10-17（0009 安装后的历史快照，已由上方重启实测及 0010 状态取代）：针对已确认的 25 矩形回退，新增 0009：撤掉 0008 全可见区放宽，保留精确裁剪，将 25 块拆成 16+9 两项，一次发布、共用一个 Present serial 和所有权/完成栅栏。共享布局不变，现有 8 项队列可原子接收最多 128 块，容量不足仍安全回退。干净 arm64 构建、签名/对齐/包内库校验、生产函数主机回归及旧版负向对照通过。已直接安装并打开 APK `88ce7f61960a3a991d20fda5256e9aab8eaedbc700ba606d6cc1b167324756a7`，未运行 zink、未停止桌面；**当前服务端仍映射旧 `7f13f30e…`，0009 尚未在服务端生效，性能目标仍未完成**。用户保存工作后的重启正在协调，不能据构建或安装结果声称帧率修复。见 [分批候选证据](../../evidence/present-copy-chunks-2026-10-17.json)。

2026-10-17（用户重启后）：**新版 APK 已在 X server 与 renderer 两端实际加载，但卡顿修复未达标**。X server 新 PID 28829 / start_ticks 40999047，Android renderer PID 852；两端从可执行映射对应 APK 读出的 SHA-256 均为 `7f13f30ef0cb3cd6928a8e5f75e786d1cc00a086408e09f8a9e190be7ee265bc`，Mali 映射与 `[1,120,15]` 正常，物理显示 mode 1 / 120.00001 Hz。无 atrace/simpleperf/dumpsys 轮询的完整 600 帧、640×480 探针为 **43.73 次提交/秒**，帧间隔 P50 25.07 ms / P95 38.04 ms，退出 0、Mali renderer 与成功标记通过。此前 3000 帧尝试在 65 秒超时，已落盘 2703 帧的内部速率约 41.79/s，保留为中断记录，不冒充完整测量。独立 6 秒诊断抓到 **214 次 `CopyFallback.4.25.0`**：最终区域 25 块仍超过 GPU 队列单项的 16 块限制；pixman 占 X server CPU 周期样本 81.65%。本场景的矩形数拒绝原因现已证实，不能继续宣称 0008 已消除软件拷贝。历史约 80.1/s 来自旧桌面负载，不构成严格同条件 A/B，不能直接把差值全归于补丁。未继续扩张视觉验收，未测屏幕新内容 FPS、功耗或输入延迟；保留当前会话，未再次重启，追踪已关闭。见 [重启后验收证据](../../evidence/present-fragmented-post-restart-2026-10-17.json)。

2026-10-17（直接安装后历史快照，已由上方用户重启后状态取代）：按用户最新指示，已覆盖安装候选 APK 并直接打开 Termux:X11，未运行 zink 脚本、未停止桌面，Linux 前缀与链接未改。已安装 APK SHA-256 为 `7f13f30ef0cb3cd6928a8e5f75e786d1cc00a086408e09f8a9e190be7ee265bc`。**当前为新 renderer / 旧 X server 的混合运行态，0008 服务端修复尚未生效**：Android 应用新 PID 20995 映射 APK 哈希为 `7f13f30e…`；独立 `termux-x11` 仍为 PID 20493 / start_ticks 39126354，从其已删除映射对应的 `map_files` 读出 APK 哈希仍为原 `e5aa6b77…`。直接打开 Activity 不会热换独立 X server 的 Present 实现。现有 X11 连接及 `[1,120,15]` 保持可用；未进行新版服务端的 A/B 或视觉验收。保持当前会话，另行安排 X server 重启后须重新核对映射；不得据安装成功声称卡顿已修复。见 [直接安装证据](../../evidence/present-fragmented-install-2026-10-17.json)。

2026-10-17（构建完成时快照，后续安装状态见上）：碎片化 Present damage **候选 APK 已完成干净 arm64 构建，当时尚未安装**。首次正式构建发现 0008 直接修改 xserver 子模块与嵌套补丁顺序不兼容；现已将 Present 改动纳入 `patches/xserver.patch`，保留交接版本的运行逻辑。全部补丁按正式顺序以 `--fuzz=0` 应用，新对象编译/链接与离线 APK 打包通过；签名与旧包一致，16 KiB ZIP 对齐、CRC、包内原生库哈希核对通过。候选 SHA-256 `7f13f30ef0cb3cd6928a8e5f75e786d1cc00a086408e09f8a9e190be7ee265bc`，构建输出 `build/x11-candidate-20261017/candidate.apk`。线上仍为下述 `e5aa6b77…` APK，Linux 前缀和系统链接未改，旧 APK 已另存回退。**pixman CPU 拷贝已有证据，具体拒绝原因仍待新版 CopyFallback 埋点确认**；完整可见区裁剪后仍可能超过 16 块，不能保证全部留在 GPU 路径。真实窗口/弹窗/IME 与 A/B 帧率、功耗均未验证。保存全部工作并明确授权停桌面后才部署，停止会结束当前对话客户端。见 [候选构建证据](../../evidence/present-fragmented-candidate-2026-10-17.json)。

2026-10-16：按用户要求，将统一 gpu-run、Termux 桌面入口及当前 profile-display 工具默认值同步为 **120 FPS**；普通桌面、GPU 桌面和 Widget 共用同一入口。Android 实际显示模式约 120 Hz、peak_refresh_rate=120，保留系统动态降频能力。配置和安装清单已更新；**当时配置尚未生效**：X11 仍以 -max-fps 60 运行，旧桌面/应用继承的 60 不会热更新；保存工作并正常停止/从 Widget 重开后才完整生效，重复点击已有 Widget/单实例不会重载。用户随后保存工作并用 zink 脚本正常重开，**120 已在运行态生效**：X11 `-max-fps 120`、根窗口 `_TERMUX_X11_DISPLAY_CLOCK=[1,120,15]`、模式 1（120.00001 Hz）、SurfaceFlinger 该图层测量周期 8.333 ms。生效不等于稳定 120 张新内容/秒：**不加采样工具**时 3000 帧小窗口探针平均 80.1 fps，图层呈现间隔中位数 8.58 ms（约 117 fps），约每 6–9 帧一次 25–30 ms 停顿；仅移动光标时该图层按 8.43 ms（约 118 fps）连续呈现，但 X 服务端 CPU 从 79 升到 161 ms/s（光标触发整幅重绘）。Mali 不是该样本的瓶颈（拷贝批次 p50 2.06 ms、交换 p50 0.57 ms、就绪等待低于 0.1 ms）。早前 38–40 fps 样本是在 atrace 与每秒 dumpsys 采样下取得，属采样条件，不能当正常帧率。功耗、输入延迟与长期稳定性仍未测。证据见 [120 FPS 配置](../../evidence/fps120-2026-10-16.json) 与 [运行诊断](../../evidence/fps120-runtime-diagnosis-2026-10-16.json)，后续计划见 [鼠标与功耗专项](../gpu-optimization-plan.md#2026-10-16-鼠标交互与-120-fps-专项)。

2026-10-15：已切换并实际运行 `/opt/pad7spro-gpu-r3.5-repro-20261015`，APK SHA-256 `e5aa6b775418830f287cef03ba780e8503d3c939e60d5287c312149bd63fd77c`。Linux 与 arm64 X11 从固定源码/新对象目录重建；Mali/AHB、两个最终屏幕图案各 49152 像素零差异、10×3 帧 oldSwapchain 重建通过。重开的助手 GPU 实际映射新前缀和原厂 Mali。首批测量/恢复工具已修正，未宣称新增帧率、功耗或延迟收益。[实施与切换证据](../../evidence/optimization-2026-10-15.json)。

本次桌面切换中断了承载对话的客户端；用户随后明确不要再为测试结束当前对话会话。后续使用独立进程/窗口，不主动停止当前桌面。旧 `/opt/pad7spro-gpu-r3.5` 与原 APK 已保留作为回退，不能将旧进程/PID 或旧默认路径继续当当前状态。以下 2026-10-13 内容为 r3.5 交付历史。

更新：2026-10-13。用户明确要求全域替换：r3.5 APK 已安装、gpu-run/gpu-launcher 已切换、桌面已正常重开；实际新 APK 和桥接映射见 [全域替换证据](../../evidence/r3.5-global-switch-2026-10-13.json)。Termux 三种启动入口继续追随统一 gpu-run，Mali / GaneshVulkan / ANGLE Vulkan / Zink 保留。下方 r3.4.1 和失败记录为历史，不代表当前运行版本。功耗、精确输入延迟和长期稳定性仍未确认。

更新：2026-10-13。接手先读本页，再核对设备；历史文档、旧记忆和 build 目录名称不能代替运行状态。

- 默认入口（2026-10-17）：gpu-run / gpu-launcher → `/opt/pad7spro-gpu-fps-20261017/bin/`；`/opt/pad7spro-gpu-r3.5-repro-20261015` 保留回退。r3.3、r3.4.1、r3.4.3 独立前缀保留。最新检查见 [r3.5 迭代](../r3.5-efficiency.md)。
- 原厂 Mali-G925 / Vulkan 1.3.278 保留。Chromium/Electron：二维 Skia 原生 Vulkan，WebGL ANGLE Vulkan。普通 OpenGL：Mesa Zink。CC Switch：WebKit 专用硬件策略和 SHM。
- 原生分辨率；新会话默认 `X11_MAX_FPS=120`、`PAD_GPU_MAX_FPS=120`（2026-10-16 配置更新；已确认运行态为 120）、`PAD_GPU_X11_COLOR_MODE=bgra`、`PAD_GPU_SKIA_BACKEND=native`。诊断默认关闭。没有零拷贝的承诺。
- **r3.4 回归已确认，已撤下默认入口**：用户报告浏览器与 Trae 闪烁/错位。`rectangleCount==0` 实为全图更新，旧实现错误跳帧；damage 只累计当前 AHB，没有跟踪其他轮换缓冲。独立逐像素回归在旧版稳定报出 stale pixels。原件与原前缀保留，历史统计不改值。
- r3.4.1 优化版保留作为稳定回退 `/opt/pad7spro-gpu-r3.4.1-opt1`。空列表/缺提示全量拷贝并正常 Present；所有 AHB 累积变化，成功提交后只清当前缓冲；重叠/相邻 damage 先合并再判断面积与超限，保留小区域拷贝和全量命令复用。原始 r3.4.1 候选保留于 `/opt/pad7spro-gpu-r3.4.1`。详见 [r3.4 审查与修复](../r3.4-damage-aware-copy.md)。
- 正常使用不创建逐帧日志。`PAD_GPU_WSI_TRACE=1` 才记录复制像素预算、提示数量，首帧及每 128 次 Copy 输出一次有界快照，能够核查应用是否实际进入局部路径。
- 入口契约不变：gpu-run 为 0755，桌面/菜单/URL/XFCE helper/CLI（chromium/chatgpt/ChatGPT/trae/trae-cn/cc-switch）/旧 gpu-app 兼容入口共用 gpu-run。LibreOffice 图标进入相同硬件环境，但不承诺其所有二维内容已硬件化。
- Termux 的 `debian-desktop.sh`、Widget `debian-zink.sh`、手动 `mali-work/desktop-zink.sh` 共用当前 GPU 桌面入口；三个设备文件与仓库参考文件逐字节一致（UID/GID 10305、0700）。命令行/TUI 与 MySQL 不属于图形渲染任务。
- 当前已安装且 X server / renderer 均实际映射的 APK SHA-256：`88346b5831c33e585d467bbf0f8255b972a05dca1ffb112a03bf683404625411`；Linux 默认前缀为 `/opt/pad7spro-gpu-fps-20261017`。versionName 仍为 `1.03.01-d55f1b7-gpu-r3.5-repro`，以哈希区分。仅 arm64 新构建；包含 0009–0014，与 WSI 0012 联合检查通过。当前映射复核见本轮证据；下方 FPS 修复交付中的 `c62abdc5…` 与 PID 为前一轮快照。
- 当前 APK 映射和新测试进程见[0014 验收证据](../../evidence/deferred-copy-wake-2026-10-17.json)；[FPS 修复交付](../../evidence/fps120-release-2026-10-17.json)为先前快照，PID 每次重新核对。

## 已验证和边界

r3.4 历史测试曾通过，但按错误的“空列表等于未变”假设编写，仅检查完成标记/计数，不能证明像素正确。原数据见 [历史证据](../../evidence/r3.4-damage-aware-copy-2026-10-13.json)，不得作为可靠性或省电结论。

r3.4.1 优化版 BUILD_EXIT=0 / BUILD_OK、INSTALL_OK；Mali 与 AHB 读回退出码 0；真实窗口重建/oldSwapchain 基础测试 30×3 帧通过。逐像素 mock 在复用开/关两种模式通过，新增重叠区域优化负向对照（初版像素正确但退回整图，优化版通过）。

256×192 动画 40 帧：局部拷贝从 0→36，549888 / 1966080 个复制像素，较全图预算少 72.03%。局部动画和空列表全图变色两个真实窗口的最终帧，Android 屏幕各 49152 像素校验无误；这不是每帧物理屏幕验收。

隔离 Chromium/Trae 测试实例：GaneshVulkan、ANGLE Vulkan/Mali、优化版 WSI/sysvk 映射、GPU 崩溃计数 0；Chromium WebGL 回读 `[26,153,204,255]`。两者均实际传递增量提示；256 次受控局部 UI 更新，稳定 128 帧区间的 WSI 复制像素较全图预算分别少 99.42% / 95.26%。测试是人工小块动画，不是用户编辑/浏览工作流。全页 CSS 滚动仍按整图更新。公开证据见 [r3.4.1 优化](../../evidence/r3.4.1-optimization-2026-10-13.json)。

r3.3 证据保留：Chromium/Trae GaneshVulkan、Mali、0 GPU 崩溃；WebGL 回读 `[26,153,204,255]`；页面 rAF 35.83→58.86/s、CPU/页面帧 10.43→8.39 ms（rAF、WSI、SF 呈现与屏幕新内容 FPS 是不同指标）。r3.4.1 已完成定向窗口/renderer/局部更新验收，用户日常操作与功耗/长期稳定性仍待验收。整机功耗回落 5W→3W 含搜狗忙循环停止与 daemon 坏记录隔离的影响，不能全部记为 GPU 路径收益。

搜狗满核发生在 CursorAnchorInfo/Xposed Hook 路径；X11 现在拒绝不存在的真实 Linux 光标几何接口。修正后同一搜狗 PID 最后八个一秒样本为 0 CPU 时间。HyperCeiler 设置和范围未改。不要为了“修复”直接冻结或禁用系统服务。

MiuiDaemon NULL subclass 队列循环已有相同 PID 的因果证据。只隔离一条坏记录，原始记录/一致备份保留在 Android `/data/local/tmp/pad-gpu-root-cause-20261012/quarantine-plan`。不能整库覆盖回滚；同类事件可能复发，永久修复属于小米固件。

## 检查、回退与重启

```sh
readlink -f /usr/local/bin/gpu-run
cat "$(dirname "$(dirname "$(readlink -f /usr/local/bin/gpu-run)")")/release.json"
gpu-run doctor
gpu-run info GPU_PID
```

运行 PID 每次重新查找，不抄历史 PID。doctor 是前置检查；映射模块证明库装载，实际 renderer/Skia 状态和窗口运行才证明渲染后端。

硬件二维回退：`PAD_GPU_SKIA_BACKEND=angle gpu-run chromium`。完整回退 r3.3：把两个系统链接切回 `/opt/pad7spro-gpu-observe-20261012/bin/`，重开应用；不覆盖在用库。软件只能显式 `gpu-run --software ...`。

保存所有工作后正常停止/从 Widget 重开桌面，会加载当前前缀的新 X server 与新应用。正常停桌面会结束 chroot 应用，不要替用户未经准备地执行。入口更新本身不热换已加载程序。

入口迁移原件在 `build/entry-handoff-20261012`，原 APK/完整运行日志在忽略目录，勿提交私人 profile、APK、系统数据库或厂商库。公开证据见 `evidence/r3.4-damage-aware-copy-2026-10-13.json` 与 [r3.3 汇总](../../evidence/r3.3-native-rendering-2026-10-12.json)。

初版修复证据见 [r3.4.1 correctness](../../evidence/r3.4.1-correctness-2026-10-13.json)，其中当时冻结/未激活记录保留为历史。最新状态见 [优化验收](../../evidence/r3.4.1-optimization-2026-10-13.json)。

## 显示效率迭代历史与验收边界

r3.4.2 曾安装并运行，窗口验收失败后恢复原 APK/r3.4.1。原始失败与旧数据保留在 [升级结果](../r3.4-upgrade-results.md)。后来同一稳定版本等待前后台动画结束后，逐像素检测通过；0009 已修正 Copy 的错误 MSC+2 计算。不能继续推广历史 0008 候选。

独立 r3.4.3 与 r3.5 已构建/安装。新 APK 集中验收已经运行，在局部更新窗口的颜色检查失败后回退，尚未进入后续应用/A-B 验收。r3.5 实现下游区域复制、消费端内容修复与矩形批量绘制。各项完成/未完成范围见 [r3.5 迭代](../r3.5-efficiency.md)，正式状态以实际链接、APK、进程与集成证据为准。没有新功耗、输入延迟或长期稳定性结论。

全域切换之前的收尾记录：r3.5 四 ABI/native 与新 Java APK 已完成构建；窗口像素/重建/Chromium 核心验收通过。Trae 工具未等到窗口导致最后自动回退。按用户最新要求停止反复重启并跳过未确认项，当前会话保持 r3.4.1；r3.5 全域替换尚未完成。具体界限见 [r3.5 收尾](../r3.5-efficiency.md)。
