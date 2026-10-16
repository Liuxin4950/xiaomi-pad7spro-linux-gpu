# GPU 与显示验证

当前已部署 r3.5，最新配置及范围见 [CURRENT-STATE](CURRENT-STATE.md)，原生二维实测见 [交付报告](r3.3-native-rendering.md)。下文早期数据保留其日期，不作为新版本功耗结论。

窗口能显示、命令行有 Vulkan 参数、进程打开了 `/dev/mali0`，都不能单独证明目标应用稳定使用 GPU。验证时组合渲染器、进程、日志、实际负载和画面证据。

## 环境与目标进程

以下在 **Debian/XFCE** 会话内执行：

```sh
test -c /dev/mali0 && echo mali-node-ok
test -c /dev/binderfs/binder && test -d /dev/binderfs/binder_logs && echo android-binderfs-ok
ps -eo pid,args | grep '[t]ype=gpu-process'
xrandr --current
```

核对 X11 服务实际 `-max-fps` 参数和 X11 mode 刷新率。2026-10-07 日常实例仍为 120；仅改参考脚本不会改变当前设备。旧 APK 的该参数主要限制报告值，真正显示节拍由第二阶段补丁补齐。刷新率不是目标应用实际帧率，应另外记录 MSC、Present 和实际 swap。

多个应用并存时先确定对应 GPU PID，不能随意取第一个。将下方 `PID` 替换为实际数字：

```sh
ls -l /proc/PID/fd | grep mali0
ps -T -p PID -o pid,tid,comm
tail -n 80 /tmp/mali-gpu-launch.log
```

该启动日志不包含所有 Chromium/Electron stderr。另检查目标应用日志中 `exited unexpectedly`、`has crashed`、GPU watchdog 等记录，并记录测试期间 GPU 进程 PID 是否重建。

## 应用层确认

- Chromium 打开 `chrome://gpu`，保存功能状态与 `GL_RENDERER` / ANGLE renderer。既有记录出现 `ANGLE (ARM, Vulkan ... Mali-G925-Immortalis)`，新测试应记录完整实际值。
- 查目标 GPU 进程线程，如 `mali-mem-purge`、`mali-event-hand`、`mali-compiler`；名称可能被截断或随版本变化。
- 操作目标窗口时观察 GPU 活动。当前固件的 `/sys/class/devfreq/gpufreq/gpufreq_usage` 是频率与累计计数表，不能直接当作百分比使用率。`cur_freq` 只表示当前频率，也不能单独证明 GPU 忙碌；应结合实际 renderer、成功的渲染/读回、进程线程和帧时间。
- 设备记录提到某些 Electron 构建会改写 GPU 进程参数为 `swiftshader-webgl` 等标签。遇到这种情况记录实际 renderer 和负载，不能只凭一个参数标签判定硬件或软件渲染。

## 视觉正确性

连续测试中文输入候选框、菜单、上下文菜单、窗口遮挡、滚动和尺寸变化。应用正常映射但像素被覆盖也是失败。

AHB/GPU 直出路径不一定支持传统 X11 截图读回。验证显示问题优先使用 Android screencap 或实际屏幕观察，记录截图渠道，避免把 scrot/XGetImage 的异常当成真实画面。

## 稳定性与结论

至少记录启动次数、连续导航/操作次数、持续时长、GPU 崩溃/重建次数和视觉异常。短测通过可以表述“该应用在这组条件下完成 GPU 渲染验证”；不要由此推出所有应用、视频硬解或长期续航结论。

## 候选栈的定向实机回归

所有测试都必须同时检查成功标记和真实退出码 0。外层保留 `timeout --kill-after=3s 35s`；驱动等待和销毁本身可能无界等待，不能只依赖探针内的 fence 超时。

- `gpu-run probe`：创建 Mali 逻辑设备、提交填充指令、等待 fence、使主机内存可见并逐字校验。
- `gpu-run ahb`：CPU 写入 AHB、发送并接收句柄、释放发送端引用，再通过接收端读回校验与释放。
- `gpu-run vulkan /opt/候选/bin/probe-present --cycles 50 --frames 3 --replace`：在同一进程中绘制、使用 oldSwapchain 替换并销毁；加 `--mailbox` 覆盖 MAILBOX，加 `--bgra` 覆盖真实 BGRA render → RGBA AHB 转换。
- `gpu-run gl glxinfo -B` 只验证上下文与 renderer；必须另测 `glxgears` 或目标应用的真实窗口，防止“识别 Mali 但 swapchain 失败”。

WSI mock 回归入口为 `tests/run-wsi-regression.sh PATCHED_WSI_SOURCE WSI_CMAKE_BUILD BRIDGE_DEPS_PREFIX`。它检查创建/销毁计数、deferred/alias、分配失败、延迟 producer fence、线程取消、连接断开、oldSwapchain 并发和 BGRA 转换；不代替真实显示测试。

## 增量复制专项验收

`probe-present --regions` 覆盖重叠 damage、轮换缓冲；`--empty-regions` 持续变色并验证空列表仍完整复制/呈现。默认关闭诊断，测试用 `PAD_GPU_WSI_TRACE=1` 核查 `copied_pixels/full_copy_pixels` 和 region 提示实际使用；这是复制工作量，不能充当功耗或屏幕 FPS。mock 逐帧比较完整目标图，物理屏幕抽查另记检查帧与范围。

本轮截图原始色空间 ID 为 2（[AOSP screencap 定义](https://android.googlesource.com/platform/frameworks/base/+/android-15.0.0_r1/cmds/screencap/screencap.cpp)），检查按 sRGB 到 Display P3 转换后的预期字节进行；不能直接把未经色空间转换的屏幕 RGB 与 Vulkan UNORM 字节等同。实测与限定见 [r3.4.1 优化证据](../evidence/r3.4.1-optimization-2026-10-13.json)。

## r3.4.2 显示链路候选验收

源码/构建通过与实际显示效果分开。候选 APK 必须在保存工作后安装并正常重开桌面，核对 APK/server 映射、`_TERMUX_X11_DISPLAY_CLOCK` 和 WSI 实际协商结果，再进行 r3.3 / candidate timer / candidate auto 交替对照。APK 自身空闲变化需与原 APK 独立 A/B，不能归入仅切换桥接的成绩。统一的工具、Perfetto 配置、帧 ID 关联与缺失数据规则见 [显示效率技术交付](r3.4-display-efficiency.md)。


## 当前显示测量工具

2026-10-15 起，profile-display 默认基线从当前 gpu-run 解析；必须显式选择候选或只测当前基线，不再默认 r3.3/r3.4.2。默认尺寸取实际 X11，runtime 跟随用户环境；`--fullscreen` 必须显式请求。

```sh
python3 scripts/profile-display.py --baseline-only --runs 1 --seconds 8 --output build/current-display
python3 scripts/profile-display.py --candidate /opt/my-installed-candidate --runs 3 --seconds 8 --output build/candidate-display
```

可指定 `--android-root`、`--server-pid`、`--surface-layer`、尺寸和 FPS。动态采样优先识别唯一 BLAST 内容层，多个内容层则拒绝猜测；静止场景默认不轮询 SurfaceFlinger，避免干扰 CPU/空闲结果。`--trace` 才启用有界诊断。当前工具仍依赖 Android dumpsys 输出，未知格式会明确作废样本，不保证跨固件解析兼容。

结果保存实际前缀/release、探针与入口哈希、条件前后快照、有效性及无效原因。所有数据都不是整机功耗测量；Surface 时间是整个 X11 层，可能包含其他应用的提交，不能当成探针独占 FPS。前后台切换或 Surface 重建期间缺少呈现数据时保留无效记录，不据此判断 GPU 回归。窗口最终像素、每帧新内容、输入因果与长期稳定需单独验收。
