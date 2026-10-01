# 参考脚本

来自 2026-10-01 的设备快照。除 `termux/desktop-zink.sh` 的帧率默认值由 120 调整为 60、增加说明注释外，其余脚本保持原样。文件来源、变更与哈希见 [reference-manifest.json](../evidence/reference-manifest.json)。

这些脚本依赖已经安装好的 chroot、桥接库和修补版 Termux:X11，并非从零安装工具。实际配置与命令见 [configuration.md](../docs/configuration.md)。

`debian-shell.sh` 和 `debian-stop.sh` 包含整个 rootfs 的进程清理、挂载及调度逻辑，不能在其他任务仍使用该 chroot 时调用停止。用于公共发行前，应整理与 GPU 无关的 CLI 模式、固定路径、权限与调度策略，并在干净设备验证。

参考目录的来源授权尚待最终核实，不能以“公开草稿”替代许可证；见 [LICENSE-STATUS.md](../LICENSE-STATUS.md)。
