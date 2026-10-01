# GPU 与显示验证

窗口能显示、命令行有 Vulkan 参数、进程打开了 `/dev/mali0`，都不能单独证明目标应用稳定使用 GPU。验证时组合渲染器、进程、日志、实际负载和画面证据。

## 环境与目标进程

以下在 **Debian/XFCE** 会话内执行：

```sh
test -c /dev/mali0 && echo mali-node-ok
test -c /dev/binderfs/binder && test -d /dev/binderfs/binder_logs && echo android-binderfs-ok
ps -eo pid,args | grep '[t]ype=gpu-process'
xrandr --current
```

确认 X11 服务实际启动参数含 `-max-fps 60`，并检查 X11 mode 刷新率。刷新率不是目标应用的实际帧率；需要 Present 采样验证时另记录采样方法和区间。

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
- 操作目标窗口时观察 GPU 活动。Android 设备侧可读 `/sys/class/devfreq/gpufreq/gpufreq_usage`，路径是本机特定实现；它是整台设备的负载，需排除其他 Android 应用干扰。
- 设备记录提到某些 Electron 构建会改写 GPU 进程参数为 `swiftshader-webgl` 等标签。遇到这种情况记录实际 renderer 和负载，不能只凭一个参数标签判定硬件或软件渲染。

## 视觉正确性

连续测试中文输入候选框、菜单、上下文菜单、窗口遮挡、滚动和尺寸变化。应用正常映射但像素被覆盖也是失败。

AHB/GPU 直出路径不一定支持传统 X11 截图读回。验证显示问题优先使用 Android screencap 或实际屏幕观察，记录截图渠道，避免把 scrot/XGetImage 的异常当成真实画面。

## 稳定性与结论

至少记录启动次数、连续导航/操作次数、持续时长、GPU 崩溃/重建次数和视觉异常。短测通过可以表述“该应用在这组条件下完成 GPU 渲染验证”；不要由此推出所有应用、视频硬解或长期续航结论。
