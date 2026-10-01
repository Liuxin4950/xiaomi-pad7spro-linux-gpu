# 配置、启动和停止

## 参考脚本

| 文件 | 运行环境 | 目标路径/作用 |
|---|---|---|
| `reference/termux/debian-shell.sh` | Termux | `~/debian-shell.sh`，挂载、会话及清理公共逻辑 |
| `reference/termux/desktop-zink.sh` | Termux | `~/mali-work/desktop-zink.sh`，启动 X11/XFCE 与 Android 资源绑定 |
| `reference/termux/debian-stop.sh` | Termux | `~/debian-stop.sh`，结束该 Debian chroot 全部进程及挂载 |
| `reference/chroot/gpu-app.sh` | Debian | `/opt/mali-bridge-canary/bin/gpu-app.sh`，三个应用的统一渲染入口 |

这些是当前机器专用参考，不是安装器。公共脚本还保留与 GPU 无关的 CLI 模式和调度逻辑；正式发行前应拆分或说明。未核实授权前不应把参考目录当成已授权的公共发行物。

## 重要配置

| 配置 | 参考值 | 原因 |
|---|---|---|
| Rootfs | `/data/linux/debian` | 现有脚本写死，修改需同时核对所有脚本 |
| Display | `:1` | 避开设备上的其他 X server；启动器支持 `DEBIAN_DISPLAY` |
| X11 DPI | `120` | 参考值，支持 `X11_DPI`；不等于 Android 系统 DPI |
| X11 帧率上限 | `60` | 用户选定的功耗与流畅度取舍；需要修补版 X11 |
| 分辨率 | 保留原生 | 功耗对照首轮不同时改变分辨率 |
| ICD | 主基线 `sysvk_icd.json` | 当前应用仍依赖 `/opt/mali-bridge` |
| libhybris / WSI | canary 目录 | 当前 Chromium、ChatGPT、Trae 使用的路径 |

公开参考脚本将设备快照中的 `-max-fps 120` 整理成 `-max-fps 60`，没有修改用户设备。默认值的语法检查通过；部署后的运行与功耗仍需重新核验。不要用不含限帧补丁的上游 APK 搭配该参数。

## 已部署环境中的日常命令

在 **Termux** 中启动桌面：

```bash
bash ~/mali-work/desktop-zink.sh
```

在 **运行中的 Debian/XFCE** 中启动应用：

```sh
DISPLAY=:1 /opt/mali-bridge-canary/bin/gpu-app.sh chromium
DISPLAY=:1 /opt/mali-bridge-canary/bin/gpu-app.sh chatgpt
DISPLAY=:1 /opt/mali-bridge-canary/bin/gpu-app.sh trae
```

结束工作并保存文件后，在 **Termux** 中停止整个环境：

```bash
bash ~/debian-stop.sh
```

桌面启动与应用启动是不同步骤。应用图标统一调用 `gpu-app.sh`；不能在 `.desktop` 中额外堆叠 ANGLE 参数或 preload。Trae 旧 `gl-egl` 路径已弃用。

缺少前置文件或 binderfs 时应用入口返回 `78` 并记录 `/tmp/mali-gpu-launch.log`。它禁用软件 rasterizer，但这不等于“所有图形环节绝无 CPU 回退”，最终结果仍需按 [验证方法](validation.md)核对。
