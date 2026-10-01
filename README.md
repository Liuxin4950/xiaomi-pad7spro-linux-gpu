# Xiaomi Pad 7S Pro Linux GPU

在已取得 root 权限的小米平板 7S Pro 上，使 Debian chroot 中部分 Linux 图形应用通过桥接调用 Android 原厂 Vulkan 驱动，并用 Termux:X11 显示。

**状态：预发布开发与验证。** 方案已在作者设备上运行。此目录已加入固定依赖版本、完整 libhybris/WSI 补丁、自行编写的 sysvk/AHB 桥接组件和统一构建入口。首次干净构建、安装器与实机运行验证仍在进行，当前尚不是已验收的发行包。

**2026-10-01 实际进展：** 固定源码的完整构建及独立安装已通过。新栈能识别 Mali-G925，但销毁实例时仍发生 `free(): invalid pointer`；换回既有 libhybris 后同探针正常退出。当前不要替换日常环境。见 [验证状态](docs/development-status.md)。

## 适用环境

| 项目 | 核对记录 |
|---|---|
| 设备 | Xiaomi Pad 7S Pro，型号 `25053RP5CC` |
| SoC / GPU | 玄戒 XRING O1 / Arm Immortalis-G925；依设备既有 GPU 记录 |
| Android | 16，API 36 |
| HyperOS | `OS3.0.303.0.WOTCNXM` |
| Linux | Debian 13.7，arm64，root chroot |
| 桌面 | XFCE；当前配置关闭 XFWM 合成器 |
| Termux | `0.118.3` |
| Termux:X11 | `1.03.01-d55f1b7-29.09.26`，另带本项目的 Present/限帧补丁 |
| 参考显示配置 | 原生分辨率，`-max-fps 60` |

版本信息于 2026-10-01 读取。运行效果主要依据 2026-09-27 至 09-29 的设备记录，本次整理未重新启动桌面测试。其他机型、GPU、固件与 proot 环境尚未验证。项目不提供取得 root 权限的步骤。

## 已记录的能力与边界

| 应用/功能 | 状态 |
|---|---|
| Chromium | 既有记录已验证 ANGLE Vulkan/Mali 图形渲染 |
| Trae CN | 2026-09-28 起统一使用 ANGLE Vulkan；旧 `gl-egl` 入口已弃用 |
| ChatGPT 桌面应用 | 窗口与 GPU 路径有验证记录；在线内容曾受服务超时影响 |
| 中文输入候选框、Chromium/Electron 弹出菜单 | Termux:X11 GPU Present 裁剪补丁已在作者设备验证 |
| CC Switch（WebKitGTK/Tauri） | 当前仍使用 CPU 渲染；不能套用 Electron 参数 |
| 视频硬解 | 尚未接通，不能从图形 GPU 加速推断已支持 |
| 通用应用加速、长期稳定、续航改善 | 需要独立验证；没有覆盖所有应用的结论 |

## 工作原理

```text
Chromium / Electron ── ANGLE Vulkan ─┐
OpenGL 应用 ────────── Mesa Zink ────┤
                                  ↓
Linux Vulkan loader → sysvk → libhybris → Android Vulkan 驱动 → Mali
                  ↘ WSI / AHardwareBuffer → 修补后的 Termux:X11 → Android 显示
```

核心配置包括绑定 Android **已有**的 binderfs、分开保存主基线与 canary 库、为不同应用选定渲染入口，以及修复 Termux:X11 的 GPU Present 遮挡裁剪。详见 [架构](docs/architecture.md)。

## 文档

- [复现流程与当前缺口](docs/setup.md)
- [从固定源码构建](docs/build.md)
- [配置、启动和停止](docs/configuration.md)
- [GPU 与显示验证](docs/validation.md)
- [功耗和稳定性测试](docs/benchmarks.md)
- [已知问题](docs/known-issues.md)
- [上游组件与来源](THIRD_PARTY.md)
- [许可证状态](LICENSE-STATUS.md)
- [Termux:X11 补丁与构建](patches/termux-x11/README.md)

`reference/` 是现有安装的参考脚本，依赖已部署的 `/opt/mali-bridge` 和 `/opt/mali-bridge-canary`，不承担安装桥接库的工作。其中桌面参考脚本整理为默认 60 FPS；该默认值只完成语法核验，功耗效果仍需同任务实测。

## 反馈与贡献

报告问题时提供机型、系统/软件版本、使用的脚本版本、复现步骤、实际结果与预期结果。图形问题附渲染器信息、GPU 进程稳定性和遮挡/菜单画面；功耗问题附测量条件和原始采样。日志先移除账号、令牌和个人内容。

新机型或新应用只有在复现与验证记录齐全后才加入支持表。欢迎围绕明确组件提交小范围修改，并保留上游版权及许可证。本草稿发布前仍需落实新增文件的许可证，见 [许可证状态](LICENSE-STATUS.md)。
