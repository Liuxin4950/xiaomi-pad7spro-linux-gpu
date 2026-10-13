# 当前运行基线：r3.4.1

更新：2026-10-13。接手先读本页，再核对设备；历史文档、旧记忆和 build 目录名称不能代替运行状态。

- 默认入口：gpu-run / gpu-launcher → `/opt/pad7spro-gpu-r3.4.1-opt1/bin/`。实际安装与重启检查见 [升级结果](r3.4-upgrade-results.md)。r3.4.1 与 r3.3 回退前缀完整保留。
- 原厂 Mali-G925 / Vulkan 1.3.278 保留。Chromium/Electron：二维 Skia 原生 Vulkan，WebGL ANGLE Vulkan。普通 OpenGL：Mesa Zink。CC Switch：WebKit 专用硬件策略和 SHM。
- 原生分辨率；默认 `X11_MAX_FPS=60`、`PAD_GPU_MAX_FPS=60`、`PAD_GPU_X11_COLOR_MODE=bgra`、`PAD_GPU_SKIA_BACKEND=native`。诊断默认关闭。没有零拷贝的承诺。
- **r3.4 回归已确认，已撤下默认入口**：用户报告浏览器与 Trae 闪烁/错位。`rectangleCount==0` 实为全图更新，旧实现错误跳帧；damage 只累计当前 AHB，没有跟踪其他轮换缓冲。独立逐像素回归在旧版稳定报出 stale pixels。原件与原前缀保留，历史统计不改值。
- r3.4.1 优化版已安装并启用 `/opt/pad7spro-gpu-r3.4.1-opt1`。空列表/缺提示全量拷贝并正常 Present；所有 AHB 累积变化，成功提交后只清当前缓冲；重叠/相邻 damage 先合并再判断面积与超限，保留小区域拷贝和全量命令复用。原始 r3.4.1 候选保留于 `/opt/pad7spro-gpu-r3.4.1`。详见 [r3.4 审查与修复](r3.4-damage-aware-copy.md)。
- 正常使用不创建逐帧日志。`PAD_GPU_WSI_TRACE=1` 才记录复制像素预算、提示数量，首帧及每 128 次 Copy 输出一次有界快照，能够核查应用是否实际进入局部路径。
- 入口契约不变：gpu-run 为 0755，桌面/菜单/URL/XFCE helper/CLI（chromium/chatgpt/ChatGPT/trae/trae-cn/cc-switch）/旧 gpu-app 兼容入口共用 gpu-run。LibreOffice 图标进入相同硬件环境，但不承诺其所有二维内容已硬件化。
- Termux 的 `debian-desktop.sh`、Widget `debian-zink.sh`、手动 `mali-work/desktop-zink.sh` 共用当前 GPU 桌面入口；三个设备文件与仓库参考文件逐字节一致（UID/GID 10305、0700）。命令行/TUI 与 MySQL 不属于图形渲染任务。
- 当前 APK：已恢复原 gpu-direct，SHA-256 `c451d41fc1424147ae4dc07db4d062985f9d10d20084bd7facfe805bfe2bc6ad`。r3.4.2 安装曾成功，新版真实窗口验收失败后已回退 APK 与统一入口。
- **回退后的实际映射已核对**：XFCE PID 14659、助手 GPU PID 14854 加载 r3.4.1 与原厂 Mali；X server PID 14576 运行恢复后的原 APK。历史 PID 不再代表当前进程。

## 已验证和边界

r3.4 历史测试曾通过，但按错误的“空列表等于未变”假设编写，仅检查完成标记/计数，不能证明像素正确。原数据见 [历史证据](../evidence/r3.4-damage-aware-copy-2026-10-13.json)，不得作为可靠性或省电结论。

r3.4.1 优化版 BUILD_EXIT=0 / BUILD_OK、INSTALL_OK；Mali 与 AHB 读回退出码 0；真实窗口重建/oldSwapchain 基础测试 30×3 帧通过。逐像素 mock 在复用开/关两种模式通过，新增重叠区域优化负向对照（初版像素正确但退回整图，优化版通过）。

256×192 动画 40 帧：局部拷贝从 0→36，549888 / 1966080 个复制像素，较全图预算少 72.03%。局部动画和空列表全图变色两个真实窗口的最终帧，Android 屏幕各 49152 像素校验无误；这不是每帧物理屏幕验收。

隔离 Chromium/Trae 测试实例：GaneshVulkan、ANGLE Vulkan/Mali、优化版 WSI/sysvk 映射、GPU 崩溃计数 0；Chromium WebGL 回读 `[26,153,204,255]`。两者均实际传递增量提示；256 次受控局部 UI 更新，稳定 128 帧区间的 WSI 复制像素较全图预算分别少 99.42% / 95.26%。测试是人工小块动画，不是用户编辑/浏览工作流。全页 CSS 滚动仍按整图更新。公开证据见 [r3.4.1 优化](../evidence/r3.4.1-optimization-2026-10-13.json)。

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

入口迁移原件在 `build/entry-handoff-20261012`，原 APK/完整运行日志在忽略目录，勿提交私人 profile、APK、系统数据库或厂商库。公开证据见 `evidence/r3.4-damage-aware-copy-2026-10-13.json` 与 [r3.3 汇总](../evidence/r3.3-native-rendering-2026-10-12.json)。

初版修复证据见 [r3.4.1 correctness](../evidence/r3.4.1-correctness-2026-10-13.json)，其中当时冻结/未激活记录保留为历史。最新状态见 [优化验收](../evidence/r3.4.1-optimization-2026-10-13.json)。

## 显示效率下一阶段候选（2026-10-13）

r3.4.2 display-clock-candidate-1 已独立构建/安装于 `/opt/pad7spro-gpu-r3.4.2-display`，候选 APK 未安装，默认仍为本页 r3.4.1。已实现 X11/WSI 显示时钟协商、下游 Present 限队列、按 Damage/光标/待完成帧请求 Choreographer，以及默认关闭空闲统计 timer；兼容旧 APK 时仍用 timer。源码回归与旧 APK 兼容窗口通过，不是新显示链路验收。见 [完整技术迭代与待验收](r3.4-display-efficiency.md)。整链路测试需保存工作后正常重开桌面；尚无新增 P99、输入延迟、功耗或温升改善结论。

本次已获用户“已保存，可以安装并重开桌面”授权。部署与检测完成状态见 [显示链路运行结果](r3.4-display-results.md)；旧用户进程已正常关闭，历史 PID 不再作为当前映射证明。助手恢复通过统一 gpu-run，默认桥接保持 r3.4.1。

后台 r3.4.2 验收失败发生在原 APK 基线准备阶段：worker 进入 PID 1 的 Android 挂载命名空间，未进入正常 Termux 桌面的挂载命名空间，因此没有 /proc、/dev/mali0，也检测不到 X11。已修正 worker 的检测/恢复调用并以实际桌面命名空间通过 doctor；没有重新启动部署程序。三个设备脚本与仓库引用仍逐字节一致，统一入口实际运行 r3.4.1。尚未取得新显示链路的 A/B 数据。

用户最新明确要求更新至 r3.4.2 并安装 APK。安装命令已返回 Success，系统入口已切换；先前“候选未安装”和 r3.4.1 默认的记录属于历史阶段。当前准确状态以 [升级结果](r3.4-upgrade-results.md) 为准。

本次用户明确要求安装并更新到 r3.4.2。部署结果：`upgrade_verification_failed`；实际默认前缀 `/opt/pad7spro-gpu-r3.4.1-opt1`。前文候选未安装、旧 PID 等属于历史快照；当前以 [升级结果](r3.4-upgrade-results.md) 为准。没有新增功耗/真实输入延迟改善结论。

最新诊断：新 APK 曾公布 `[1,60,7]`，Mali 提交读回与 AHB roundtrip 通过。带前后台恢复的屏幕逐像素检测失败；同一检测在稳定 r3.4.1 上也失败，需校正 viewport/过滤造成的非 1:1 显示，不能认定所有差异都是新版内容损坏。另确认 Copy 的目标计算错误：锁定 Xorg 只有同步 Flip 才把 exec_msc 减 1，Copy 保持 target；候选把 Copy 下一目标设为 MSC+2 的依据错误，需要修正。当前仍保留 r3.4.1，不把 r3.4.2 标为完善。
