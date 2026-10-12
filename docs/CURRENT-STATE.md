# 当前唯一运行基线：r3.3

更新：2026-10-12。接手先读本页，再核对设备；历史文档、旧记忆和 build 目录名称不能代替运行状态。

- 默认入口：`/usr/local/bin/gpu-run`、`gpu-launcher` → `/opt/pad7spro-gpu-observe-20261012/bin/`。版本读该前缀 `release.json`，文件校验读 `install-manifest.json`。目录名 observe 是构建时确定的路径，不表示正在逐帧诊断，不能改名破坏 RUNPATH。
- 原厂 Mali-G925 / Vulkan 1.3.278 保留。Chromium/Electron：二维 Skia 原生 Vulkan，WebGL ANGLE Vulkan。普通 OpenGL：Mesa Zink。CC Switch：WebKit 专用硬件策略和 SHM。
- 原生分辨率；默认 `X11_MAX_FPS=60`、`PAD_GPU_MAX_FPS=60`、`PAD_GPU_X11_COLOR_MODE=bgra`、`PAD_GPU_SKIA_BACKEND=native`。诊断默认关闭。没有零拷贝或静止内容去重的承诺。
- 入口同步后的权限回归已修复：gpu-run 为 0755，真实开发菜单恢复 CC Switch / ChatGPT / Trae，互联网恢复 Chromium。源码也记录可执行位，后续同步必须检查 `test -x`；仅哈希一致不够。
- 图标、菜单、URL、XFCE 浏览器 helper、CLI `chromium/chatgpt/ChatGPT/trae/trae-cn/cc-switch`、旧 gpu-app 兼容入口共用 gpu-run。LibreOffice 图标进入相同硬件环境，但不承诺其所有二维内容已硬件化。
- Termux 的 `debian-desktop.sh`、Widget `debian-zink.sh`、手动 `mali-work/desktop-zink.sh` 共用当前 GPU 会话入口。旧普通桌面默认 llvmpipe 的分支已撤掉；命令行/TUI 与 MySQL 不属于图形渲染任务。
- 当前 APK：`1.03.01-d55f1b7-gpu-direct-12.10.26`；SHA-256 `c451d41fc1424147ae4dc07db4d062985f9d10d20084bd7facfe805bfe2bc6ad`；同证书，上游 d55f1b7 + popup/原生批处理/输入接口修正。新 X server 已重开并映射该 APK 的原生代码，启动请求为 60 fps。最终核对没有重新测量屏幕扫描帧率。
- 当前 ChatGPT 已完整重开，主进程包含原生 Vulkan 参数；GPU 子进程映射当前 WSI 与 Mali，崩溃计数 0。Chromium/Trae 的 GaneshVulkan 已独立实测；此轮没有额外采样 ChatGPT 的 Skia 名称。以后重复点已有单实例仍不能当成重启。

## 已验证和边界

Chromium/Trae 独立实例确认 GaneshVulkan、Mali、0 GPU 崩溃；WebGL 回读 `[26,153,204,255]`、错误码 0。同一可见滚动场景页面 rAF 约 35.83→58.86/s，CPU/页面帧 10.43→8.39 ms。rAF、WSI、SF 层呈现与屏幕新内容 FPS 是不同指标。整体续航、睡眠恢复、屏幕尾延迟、真实中文触控输入仍需使用中核对，不宣称所有应用/长期负载已经验收。

搜狗满核发生在 CursorAnchorInfo/Xposed Hook 路径；X11 现在拒绝不存在的真实 Linux 光标几何接口，文本/组合/selection/按键路径保留。修正后同一搜狗 PID 最后八个一秒样本为 0 CPU 时间。HyperCeiler 设置和范围未改。不要为了“修复”直接冻结或禁用系统服务。

MiuiDaemon NULL subclass 队列循环已有相同 PID 的因果证据。只隔离一条坏记录，原始记录/一致备份保留在 Android `/data/local/tmp/pad-gpu-root-cause-20261012/quarantine-plan`。不能整库覆盖回滚；同类事件可能复发，永久修复属于小米固件。

## 检查、回退与重启

```sh
readlink -f /usr/local/bin/gpu-run
cat /opt/pad7spro-gpu-observe-20261012/release.json
gpu-run doctor
gpu-run info GPU_PID
```

运行 PID 每次重新查找，不抄历史 PID。doctor 是前置检查；映射模块证明库装载，实际 renderer/Skia 状态和窗口运行才证明渲染后端。

硬件二维回退：`PAD_GPU_SKIA_BACKEND=angle gpu-run chromium`。完整 r2 回退只需把统一入口链接切回保留的 r2，重开应用；不覆盖正在映射的库。软件只能显式 `gpu-run --software ...`。

保存所有工作后正常停止/从 Widget 重开桌面，会加载当前 APK 的新 X server。正常停桌面会结束 chroot 应用，不要替用户未经准备地执行。入口更新本身不热换已加载程序。

入口迁移原件在 `build/entry-handoff-20261012`，原 APK/完整运行日志在忽略目录，勿提交私人 profile、APK、系统数据库或厂商库。当前公开数据见 [r3.3 汇总](../evidence/r3.3-native-rendering-2026-10-12.json)，细节见 [交付报告](r3.3-native-rendering.md)。
