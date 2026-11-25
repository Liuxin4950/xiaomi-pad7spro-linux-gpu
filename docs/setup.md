# 安装与更换 Termux

2026-11-11：当前为 r3.6-rc1 发布候选。[运行身份](CURRENT-STATE.md)、[候选说明与未达标项](r3.6-release.md)为准。本页分清“换 Termux、保留 Debian”与“新建整个 Linux 环境”。

## 换 Termux，保留已有 Debian/rootfs

适用：本机 `/data/linux/debian` 和 `/opt/pad7spro-gpu-fps-20261017` 仍在，root 可用，Android 端已有本项目 X11 APK。换 Termux 不需要重新编译 GPU 库。rootfs 必须放在新旧 Termux 之外的持久目录；卸载会删除的应用私有数据应先自行保存。

保存工作后正常结束旧桌面，再使用新 Termux；不要让两个 Termux 同时管理一个 rootfs，旧启动器的退出清理会影响共享桌面。

把发布包解压至新 Termux 的 HOME（不要在共享存储里直接执行），进入解压目录：

```sh
bash scripts/bootstrap-termux.sh /data/linux/debian
```

该命令安装 Termux 依赖，按实际 HOME/PREFIX 生成共享启动、root 通道、桌面、Widget 和配置文件；发布包内的同源 loader 会校验后安装。旧入口及 loader 保存到新建的 `~/.local/state/pad-gpu/termux-时间-进程号/`。不安装 X11 APK、不启动/停止桌面、不修改用户 profile。

然后启动：

```sh
bash ~/debian-desktop.sh
```

已安装 Termux:Widget 时可用 `debian-zink`。Termux 与 Widget 应来自相容的发行渠道；不由本项目重新签名。首次使用需要 root 授权，缺少已有 ADB key 时还需要批准本机 ADB 授权。新 UID 使用独立 ADB server 端口，避免沿用旧 UID 的访问规则。

新装后在系统电池设置中检查 Termux、Widget 与 X11 的后台限制；旧应用 UID/白名单不会自动代表新安装。OS4 曾重置此设置，见稳定性记录。bootstrap 不改 PowerKeeper 数据或禁用服务。

依赖已齐时可跳过 pkg，先预览再写入：

```sh
python scripts/configure-termux.py --rootfs /data/linux/debian
python scripts/configure-termux.py --rootfs /data/linux/debian \
  --apply --backup "$HOME/pad-gpu-entry-backup"
```

非默认目录通过参数指定；HOME/PREFIX 从当前 Termux 获取，必要时可显式传 `--home` / `--prefix`。不能通过 su 运行该工具，也不能拿它给另一个 UID 写文件。工具拒绝危险路径、逃逸软链、缺少依赖、既有备份目录；重复执行不重复改文件。恢复见 [接手手册](tablet-handoff.md)。

发布包包含 `artifacts/x11-companion/` 时自动使用其中的固定 loader；源码检出可用 `--companion /构建输出/x11-companion`。没有该目录时仅配置脚本，现有 `termux-x11` 依赖仍必须安装。官方 X11 需要 APK 和 Termux 侧组件两部分，见[上游说明](https://github.com/termux/termux-x11#setup-instructions)；本项目固定的修补 APK不可随意用上游 APK 替换。

启动后在 Debian 中检查：

```sh
gpu-run doctor
gpu-run probe
gpu-run ahb
```

doctor 只检查前提；probe/ahb 才验证硬件调用。窗口、输入和流畅度还需实际确认。新 Termux 的真实端到端启动尚未在卸载重装后验证；本轮完成的是隔离 HOME 的创建、幂等、转发参数、同源 loader 和故障回退测试。

## 原厂状态或全新 rootfs

当前发布包**不包含 Debian rootfs、原厂 Mali、个人密钥或修改版 bionic 二进制**。恢复出厂后不能仅执行上述 bootstrap 就获得完整桌面。适用环境为已 root 的同机型、Debian 13 arm64 root chroot + XFCE；proot、其他 GPU或 Termux 分支未获兼容保证。

1. 安装并配置自己的 root、Termux 与 X11 APK；准备持久目录中的 Debian arm64 rootfs。
2. 配置 root chroot 基础依赖、XFCE、D-Bus、中文 locale、Fcitx5。OS4 的 seccomp/clone3 差异及既有 keepcaps 依赖见接手手册；该部分尚不是本仓库的全自动安装流程。
3. 按 [构建说明](build.md) 准备依赖，固定源码构建 GPU 前缀：

```sh
bridge_prefix="/opt/pad7spro-gpu-new"
bash scripts/build.sh --prefix "$bridge_prefix" --jobs 4
bash scripts/install.sh "$(cat build/last-stage.txt)" "$bridge_prefix"
```

安装器拒绝覆盖旧前缀。实际 Android `/system`、`/vendor`、`/apex`、`/dev/mali0` 和 Android 原有 binderfs 必须可见；空 binderfs 不能替代原实例。安装器不代办 rootfs、root 授权或系统策略。

4. 按 [验证方法](validation.md) 验证候选前缀的真实 Vulkan、AHB 和窗口。通过后才设置统一入口：

```sh
ln -sfn "$bridge_prefix/bin/gpu-run" /usr/local/bin/gpu-run
ln -sfn "$bridge_prefix/bin/gpu-launcher" /usr/local/bin/gpu-launcher
ln -sfn "$bridge_prefix/bin/run-gpu" /usr/local/bin/run-gpu
ln -sfn "$bridge_prefix/bin/gpu-env" /usr/local/bin/gpu-env
```

已有安装升级应使用 `activate-release.py` 的预览、备份与恢复事务；该工具用于已有作者入口，不能代替新 Termux 的 configure 工具。现有应用不热换已映射库。

5. 在新 Termux 中运行 bootstrap 接入该 rootfs。普通应用图标使用 `Exec=/usr/local/bin/gpu-run auto 程序 %U`，保留原来的参数/占位符。Fcitx5 与 Clipman 的参考启动项在 `reference/chroot/`；根据已有 XDG ID 合并，不能新建第二个启动 ID。

安装前缀同时提供 `/usr/local/bin/run-gpu` 和 `/usr/local/bin/gpu-env`。`run-gpu 应用 参数` 是面向用户的通用硬件入口；`gpu-run 模式 应用 参数` 保留精确选择。登录 shell 或自定义会话可以执行 `source /usr/local/bin/gpu-env`，让普通 Vulkan/Zink 应用继承 Mali 环境。该全局环境只包含桥接核心变量，不注入 WebKit preload 或 Electron 参数；这些应用专用策略仍由 `gpu-run` 处理。

若要让新 chroot 的登录 Bash 自动继承 GPU 环境，先预览并准备一个新的备份目录，再由 root 写入 `/etc/profile.d/90-pad-gpu.sh`：

```sh
bash scripts/install-global-env.sh --prefix "$bridge_prefix"
bash scripts/install-global-env.sh --prefix "$bridge_prefix" \
  --apply --backup /opt/pad-gpu-profile-backup-日期
```

脚本只创建自己的 profile hook，拒绝覆盖已有同名文件；回退时依据备份回执删除本次创建的 hook。它只对 Bash shell 自动导入环境，不会替所有框架自动选择硬件 backend。

## 升级 X11 和回退

APK 和 loader 应使用同源产物，并核对 APK 证书、完整哈希及新进程实际映射。当前设备的 rc1 已安装，安装前 APK 已备份，前端/server 新进程映射一致。其他设备或干净 Termux 不应假设已安装；APK 更新会重启 X11 服务，应先保存桌面工作并按设备的安全切换流程执行。

Linux 链接、Termux 文件、APK 是独立回退对象。不要全局 pkill、覆盖映射库、关闭系统服务或自动降到软件渲染。旧安装全文保存在 [历史快照](history/2026-11-11-setup-before-termux-bootstrap.md)。
