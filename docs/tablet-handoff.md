# 平板 / 后续 AI 接手

更新：2026-10-12。当前版本 r3.3，先读 [CURRENT-STATE](CURRENT-STATE.md)。旧 r2、早期 canary 和历史实验数字不能作为当前启动配置。

## 设备入口

工作区 `/opt/pad7spro-gpu-release-test/repository`，别名 `/root/Working/xiaomi-pad7spro-linux-gpu`。容器为 Debian 13，Android rootfs 路径 `/data/linux/debian`；用户可能称其 Ubuntu，不据此另找第二个 rootfs。

- 当前完整前缀 `/opt/pad7spro-gpu-observe-20261012`，系统 gpu-run/gpu-launcher 链接到这里，版本与文件状态读 release.json / install-manifest.json。
- Termux Widget、`~/debian-desktop.sh` 和 `~/mali-work/desktop-zink.sh` 共用 GPU 桌面入口。普通桌面不再默认 llvmpipe。
- 桌面、菜单、URL、XFCE helper 和 CLI chromium/chatgpt/ChatGPT/trae/trae-cn/cc-switch 全部统一到 gpu-run。Office 图标也进入同一环境；MySQL、shell/TUI 不强加图形参数。
- 二维 Skia 原生 Vulkan；WebGL ANGLE Vulkan；GL Zink；CC Switch 使用 WebKit 适配。
- 原生分辨率，60 fps 请求与 WSI 上限；BGRA 字节契约，不设置 vblank_mode=0，不自动软件回退。

## 安全接手步骤

```sh
cd /opt/pad7spro-gpu-release-test/repository
git status --short
readlink -f /usr/local/bin/gpu-run
gpu-run doctor
gpu-run info GPU_PID
```

查当前实际进程，不抄历史 PID。doctor / 命令行参数只证明前置配置；renderer、Skia 后端和已显示窗口才是运行证据。源码修改不自动更新安装前缀；manifest / 入口 / 文档需同步。RUNPATH 固定，不能随意重命名前缀。

现在已安装 gpu-direct APK（详细版本/哈希在 CURRENT-STATE），前端批处理与输入修正已运行。存活的旧 X server 和旧 ChatGPT 主进程需要正常重开才能全部加载新代码/参数。再次点已有单实例只复用它。保存工作后，用户可正常停止桌面再从 Widget 开启；不要替用户直接全局 pkill。

## 回退和诊断

单应用硬件回退：`PAD_GPU_SKIA_BACKEND=angle gpu-run chromium`。显式 CPU 参考：`gpu-run --software chromium`。完整 r2 保留为回退目录，统一链接切回后重开应用；不覆盖在用库。

Android 核心探针现在默认跟随 rootfs 中的 gpu-run 系统链接：

```sh
su -W -c '/system/bin/sh /data/linux/debian/opt/pad7spro-gpu-release-test/repository/scripts/android-probe.sh'
```

私有运行证据/入口备份在 build，公开脱敏证据在 evidence。不要提交 APK、测试 profile、系统 DB、厂商库或私人日志。不修改系统分区/SELinux，不直接禁用系统服务。不要执行旧 disable-miui-telemetry.sh。

WSI、rAF、SF 呈现与屏幕实际新帧分开；短时电流不证明长期续航。MiuiDaemon 一条坏记录已备份隔离；搜狗忙循环已定位到 CursorAnchorInfo/Hook 路径，模块设置未改。后续若复发先抓同 PID / starttime 与真实 CPU，不要继续盲改 Vulkan。

入口与文档最新变更记录见 `evidence/entrypoints-2026-10-12.json`，渲染证据见 `evidence/r3.3-native-rendering-2026-10-12.json`。历史实测保留，不重写成新版成绩。
