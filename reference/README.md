# Termux 配套组件与启动资源

更新：2026-10-17。当前默认桥接为 `/opt/pad7spro-gpu-fps-20261017`；运行状态见 [CURRENT-STATE](../docs/CURRENT-STATE.md)。本目录保存作者设备的入口参考，精确内容及部署校验见 [资源清单](../evidence/reference-manifest.json)和 [本次同步证据](../evidence/termux-resources-2026-10-17.json)。

## 已安装组件

| 组件 | 本机版本 | 作用 |
|---|---|---|
| Termux (`com.termux`) | 0.118.3 | 提供 Bash、root/chroot 启动环境 |
| Termux:Widget (`com.termux.widget`) | 0.15.0 | 展示 `~/.shortcuts/` 中的快捷入口 |
| Termux:X11 (`com.termux.x11`) | `1.03.01-d55f1b7-gpu-r3.5-repro`，APK SHA-256 `c62abdc5…` | Android 显示端和独立 X server 使用的原生实现 |
| Termux `termux-x11-nightly` 包 | 1.03.01-5 | Termux 侧 `termux-x11` 命令；包版本与 Android APK 版本分别记录 |

这些是设备已安装版本，不表示已检查上游最新版本。本次对齐已验收修复版及配套资源；没有替换 Termux/Widget APK。Termux:API、Termux:Boot 未安装，本方案不依赖它们。更新 X11 时应使用包含本项目补丁的匹配构建，不能用无补丁的上游 APK 覆盖后仍沿用现有验收结论。

## 文件位置与职责

下表路径相对 Termux home `/data/data/com.termux/files/home`。设备五份主要脚本均为 UID/GID 10305、0700；其他设备应保留自身 Termux UID，不照抄数值。

| 仓库文件 | 设备位置 | 作用 |
|---|---|---|
| `termux/desktop-zink.sh` | `mali-work/desktop-zink.sh` | 唯一桌面实现，创建或复用 X11/XFCE，经统一 gpu-run 选择当前前缀 |
| `termux/debian-desktop.sh` | `debian-desktop.sh` | 普通桌面入口，转发到上述实现 |
| `termux/debian-zink-widget.sh` | `.shortcuts/debian-zink.sh` | Widget 桌面入口，保留参数转发 |
| `termux/debian-shell.sh` | `debian-shell.sh` | 共享挂载、模式锁、会话、看门狗及 shell/Command Code 模式 |
| `termux/debian-stop.sh` | `debian-stop.sh` | 保存工作后停止整个 chroot；`status` 只读检查，`backup` 需先停止并卸载 |
| `chroot/gpu-app.sh` | Debian `/opt/mali-bridge-canary/bin/gpu-app.sh` | 旧入口兼容转发，新图标直接用 `/usr/local/bin/gpu-run` |

脚本名中的 zink 保留兼容。桌面 OpenGL 使用 Zink，Chromium/Electron 二维使用原生 Skia Vulkan，WebGL 使用 ANGLE Vulkan；不是全部应用都经过 Zink。新会话默认 X11/WSI 上限均为 120，BGRA 字节契约保持不变。

Widget 还有 shell、stop、DSH、Code Server、Command Code 等既有入口。它们仍指向各自脚本，不强加 GPU 参数，不改用户工具或工作目录。DSH/Code Server 不属于本次图形栈的维护范围。

## 日常操作与更新生效

- 桌面已运行：直接点 Android 的 Termux:X11 图标。无需运行桌面启动脚本。
- 创建桌面：使用现有 Widget `debian-zink` 或普通 `debian-desktop.sh`。已有 XFCE 时仅复用。
- Linux 前缀更新：系统 gpu-run/gpu-launcher 链接切换后，正常重开需要换库的应用，再核对新 GPU PID 的映射；不用停止整个桌面。
- X11 APK 更新：安装 APK 与打开 Activity 不等于独立 X server 已重载。分别核对 server / renderer 的映射哈希。确需重启 server 时先保存全部工作并安排切换；停止桌面会结束 chroot 应用。

只打开现有 X11 的 Termux 命令：

```sh
su -c '/system/bin/am start --user 0 -n com.termux.x11/com.termux.x11.MainActivity'
```

不要用全局 pkill、覆盖已映射库或卸载活跃挂载来完成更新。root 身份不能代替正确的 Android binderfs 实例和命名空间。

## 同步与恢复

复用现有工具，先预览，再保留完整备份应用：

```sh
python3 scripts/activate-release.py /opt/pad7spro-gpu-fps-20261017
python3 scripts/activate-release.py /opt/pad7spro-gpu-fps-20261017 \
  --apply --backup build/独立且尚不存在的备份目录
```

工具核对安装清单，保存原链接和所有实际改动文件的内容、mode/owner/xattrs，并同步五份主要 Termux 入口。它只更新入口，不执行桌面脚本、不安装 APK、不停止会话。回退先去掉 `--apply` 查看恢复计划，确认后再应用：

```sh
python3 scripts/activate-release.py --restore build/上述备份目录 --apply
```

`activate-desktop.py` 可单独预览已知入口迁移，但实际更新优先走带备份的 activate-release。全新设备仍需按 [setup](../docs/setup.md)配置 rootfs、Termux 组件和会话，不把此目录当作从零安装器。可选 `chroot/gpu-launcher.desktop` 不是启用 GPU 的必经步骤。

许可证和第三方边界见 [LICENSE-STATUS](../LICENSE-STATUS.md)。
