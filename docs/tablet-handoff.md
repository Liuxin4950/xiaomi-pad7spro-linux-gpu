# 平板接手

更新：2026-10-07。用户已从 Termux Widget 重启并确认启动成功。当前使用完整 r2 前缀和统一桌面路由，旧混合主基线/canary 不再是日常默认。

## 工作区与当前安装

Debian 仓库路径为 `/opt/pad7spro-gpu-release-test/repository`；`/root/Working/xiaomi-pad7spro-linux-gpu` 指向它。现有远端仓库为 `Liuxin4950/xiaomi-pad7spro-linux-gpu`。更新前先检查本地修改：

```sh
cd /opt/pad7spro-gpu-release-test/repository
git status
git pull --ff-only
```

| 路径 | 当前作用 |
|---|---|
| `/opt/pad7spro-gpu-dev-20261007-r2` | 已部署的完整桥接、应用适配和探针 |
| `/usr/local/bin/gpu-run` | 链接到 r2 的统一入口 |
| `/usr/local/bin/gpu-launcher` | 链接到 r2 的可选输入框 |
| `build/sources` | 固定 revision/二进制依赖缓存 |
| `build/runs` | 独立构建、日志和 stage |
| `build/app-adaptation-20261007` | 本机应用短验收的临时 profile、日志、模块记录和截图，未纳入 Git |

源码缓存齐全时可离线继续构建；构建/安装说明见 [build.md](build.md)。修改源码不会自动更新已安装库或脚本。下一次部署应使用新的完整前缀，经验证后再切系统链接，不覆盖正在使用的 r2。

## 日常启动与桌面

Termux Widget 的 `.shortcuts/debian-zink.sh` 调用 `~/mali-work/desktop-zink.sh`。该实际脚本已迁移到统一入口，默认 X11 60 FPS、WSI 每交换链 60 FPS、BGRA 颜色契约；`HYBRIS_VULKANPLATFORM=null`，没有旧 `vblank_mode=0`。当前读取到的 X11 命令含 `-max-fps 60`。

```sh
# Termux：手动启动等价于 Widget
bash ~/mali-work/desktop-zink.sh

# Debian/XFCE：也可以直接点正常应用图标
gpu-run chromium
gpu-run chatgpt
gpu-run trae
gpu-run cc-switch
```

新会话已继承统一的 Mesa/Zink、Vulkan、hybris 和 WSI 环境，普通程序不必都经过 GPU 输入框。框架专用入口、显式 WebKit 和软件模式见 [配置说明](configuration.md)。再次点击正在运行的 Widget 会话只会复用它。

桌面只保留 Chromium、ChatGPT、Trae CN、CC Switch 和 MySQL 五个启动图标，GPU 启动器没有留在桌面。MySQL 的实际脚本已移至 `/root/.local/libexec/liutech/start-mysql.sh`，不依赖桌面其他文件，也不是 GPU 安装的一部分。

保存工作后，在 Termux 正常停止整个 chroot：

```sh
bash ~/debian-stop.sh
```

## 检查和边界

在已运行桌面中使用：

```sh
gpu-run info
gpu-run doctor
gpu-run info 目标GPU进程PID
```

不带 PID 的 `info` 只显示配置，带 PID 才显示实际映射模块。四个应用都已有新前缀下的短验收记录；Trae 最后一次短启显示正常欢迎页、GPU 使用 r2、没有触发地址预留重试。启动容错只处理精确 Oilpan cage 早期失败，不是 GPU 崩溃重启器。

Android 侧核心检查必须显式指定 r2，因为脚本默认前缀仍是 `/opt/pad7spro-gpu`。作者设备在 Termux 使用：

```sh
su -W -c 'PAD_GPU_PREFIX=/opt/pad7spro-gpu-dev-20261007-r2 /system/bin/sh /data/linux/debian/opt/pad7spro-gpu-release-test/repository/scripts/android-probe.sh'
```

脚本在私有挂载命名空间绑定现有 Android 资源，检查 Vulkan 与 AHB。`GPU_CORE_PROBES_OK` 只代表两项核心调用通过；其他 root 工具使用相应 `su` 参数。视觉问题使用 Android 截图或屏幕观察，不能只凭 X11 截图读回判断 AHB 内容。

本轮没有升级 Termux:X11 APK，`0002` 仍为候选。应用短验收和用户确认启动成功，不等于已经完成长期导航、项目工作流、休眠恢复、WebKitGTK WebGL2、视频硬解或同条件功耗验收。

接手优先阅读 `README.md`、[实现与接入](setup.md)、[配置](configuration.md)、[构建](build.md)、[验证状态](development-status.md)和 `sources.lock.json`。`activate-desktop.py` 仅迁移作者设备既有入口，不是通用干净 rootfs 安装器；当前已迁移完成，无须每次启动重复执行。
