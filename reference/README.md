# 参考脚本

该目录包含作者设备的会话/迁移入口。`debian-shell.sh`、`debian-stop.sh` 保留 2026-10-01 快照；`desktop-zink.sh` 与 `chroot/gpu-app.sh` 已于 2026-10-07 更新并部署，来源和哈希见 [reference-manifest.json](../evidence/reference-manifest.json)。

- `desktop-zink.sh` 经统一 `gpu-run` 启动 XFCE，新会话默认继承 GPU 环境和 60 FPS/BGRA 配置。
- `gpu-app.sh` 是旧路径的兼容转发；当前正常图标直接使用 `/usr/local/bin/gpu-run`。
- `gpu-launcher.desktop` 是可选菜单工具，不是启用 GPU 的必经步骤；作者桌面已移除该额外图标。

这些脚本依赖已安装的 chroot、完整桥接前缀与匹配的 Termux:X11，不是从零安装器。实际流程见 [setup](../docs/setup.md) 和 [configuration](../docs/configuration.md)。

`debian-shell.sh` 与 `debian-stop.sh` 管理整个 rootfs 的进程、挂载及调度，停止会结束该 chroot 内的工作。不要在其他任务仍使用此环境时调用，也不要直接复制到不同布局的设备而跳过核对。

许可证和第三方边界见 [LICENSE-STATUS.md](../LICENSE-STATUS.md)。公开源代码不等于所有新设备和冷 rootfs 已验收。
