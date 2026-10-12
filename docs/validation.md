# GPU 与显示验证

当前版本 r3.3，最新配置及范围见 [CURRENT-STATE](CURRENT-STATE.md)，原生二维实测见 [交付报告](r3.3-native-rendering.md)。下文早期数据保留其日期，不作为新版本功耗结论。

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
