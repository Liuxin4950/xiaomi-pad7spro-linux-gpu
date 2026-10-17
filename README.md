# Xiaomi Pad 7S Pro Linux GPU

让已 root 的小米平板 7S Pro 中的 Debian arm64 chroot 图形软件调用 Android 原厂 Mali Vulkan 驱动，并通过 Termux:X11 显示。

2026-10-17：用户明确以当前结果作为 **r3.5 最终版本**，发行标识 `r3.5-final-20261017`。本轮优化已收尾；未达到稳定真实 120 帧、长期功耗/输入延迟等项目作为已知限制保留，不再自动执行旧计划或更换 APK。

当前身份、结果与边界见 [最终 r3.5 说明](docs/r3.5-efficiency.md)、[CURRENT-STATE](docs/CURRENT-STATE.md) 和[最终清单](evidence/r3.5-final-2026-10-17.json)。默认页面约 112–116 rAF/s，712704 个物理像素零差异；定版不代表稳定真实显示 120 帧或长期续航已验收。

数据位置：公开证据和校验在 `evidence/`、`evidence/SHA256SUMS`；原始 CSV/JSON/trace/截图与 APK 仍保留在 `build/`。另有仓库外本地归档 `/opt/pad7spro-gpu-release-test/releases/r3.5-final-20261017/`，包含源码快照、最终 APK、Linux 前缀、原始数据清单和压缩包、SHA256SUMS。该归档是本机私有备份，不自动发布到互联网；不含用户 profile、SDK 缓存或签名私钥。

## 日常使用

1. 新建桌面时，在 Termux:Widget 中点 `debian-zink`；普通 `debian-desktop.sh` 调用相同入口。桌面已运行时可直接打开 Termux:X11。
2. 进入 XFCE 后直接使用原来的应用图标。桌面、菜单和 URL 入口已统一到新 GPU 栈。
3. 当前会话默认带有 Zink、Vulkan ICD/WSI 和 BGRA 传输配置。兼容的 OpenGL/Vulkan 软件通常可以直接继承这些设置；GPU 应用启动器是可选菜单工具。

给新应用设置快捷方式时，可保留原来的程序参数和 `%U` / `%F` 占位符，使用统一入口：

```ini
Exec=/usr/local/bin/gpu-run auto /path/to/application
```

`auto` 识别已知 Chromium/Electron 名称及保守的 Electron 发行布局；未知程序接收硬件环境。特殊框架可明确选择：

```sh
gpu-run gl application           # OpenGL → Mesa Zink
gpu-run vulkan application       # 原生 Vulkan
gpu-run electron application     # Electron → ANGLE Vulkan
gpu-run webkit application       # WebKitGTK 4.1 专用适配
gpu-run cc-switch               # 已适配的 CC Switch
gpu-run --software auto application  # 显式软件渲染
```

入口不会因硬件启动失败自动重试 CPU 路径。软件自己选择 CPU 绘制、要求驱动缺失的特性或使用其他图形接口时，仍需单独判断兼容性。当前并未接通视频硬解。

## 工作原理

```text
Chromium / Electron 二维 → Skia Vulkan ┐
WebGL → ANGLE Vulkan ─────────────────┤
OpenGL / WebKitGTK → Mesa Zink ─────┤
原生 Vulkan ────────────────────────┤
                                   ↓
Linux Vulkan loader → sysvk → libhybris → Android Vulkan HAL → Mali-G925
                            ↘ WSI / AHardwareBuffer → Termux:X11 → Android 显示
```

WebKitGTK 适配使用 GPU 合成与共享内存帧传输，不能称作端到端零拷贝。当前 X11 协议模式公开真实 BGRA 渲染图像，将其字节用 GPU 复制到私有 RGBA AHardwareBuffer，匹配 Xorg 的 BGRA 字节契约，避免红蓝交换。

新栈将 ICD、libhybris、AHB wrapper、WSI 与私有 bionic override 放在同一个安装前缀中。应用级 WSI 呈现默认上限为 120 FPS（2026-10-16 更新；已有会话需正常重开）；它不是整个 Android 的 GPU 工作上限，也没有实现静止内容去重。详见 [架构](docs/architecture.md)和 [实现说明](docs/implementation.md)。

## 适用环境与验证范围

| 项目 | 本机记录 |
|---|---|
| 设备 | Xiaomi Pad 7S Pro，`25053RP5CC` |
| GPU | Arm Immortalis-G925；实际 Vulkan 名称 `Mali-G925-Immortalis` |
| Android / HyperOS | Android 16、API 36 / `OS3.0.303.0.WOTCNXM` |
| Linux | Debian 13 arm64、root chroot、XFCE，关闭 XFWM 合成器 |
| Mesa | 25.0.7；Zink 报告 OpenGL 3.2，仍缺部分基础 Vulkan 特性 |
| Termux | `0.118.3` |
| Termux:Widget | `0.15.0`，桌面快捷入口追随统一 gpu-run |
| 当前 Termux:X11 APK | `1.03.01-d55f1b7-gpu-r3.5-repro`，SHA-256 `88346b58…`，以完整哈希区分同名构建 |
| 当前启动默认 | 原生分辨率，`X11_MAX_FPS=120`、`PAD_GPU_MAX_FPS=120` |

设备型号/固件基线来自 2026-10-01；Termux、Widget、X11 和入口清单已于 2026-10-17 重新核对，见 [Termux 配套资源](reference/README.md)。其他机型、固件、GPU、proot 和非 root/sandbox 配置未验证。

| 应用/能力 | 当前状态 |
|---|---|
| Vulkan / AHB | 逻辑设备、真实指令提交与读回；AHB 发送/接收、读回和释放通过 |
| OpenGL / Zink | 实际齿轮窗口、Mali renderer 和正确 RGB 画面通过 |
| Chromium | ANGLE Vulkan/Mali、WebGL/WebGL2、像素读回与 Android 画面通过 |
| ChatGPT 桌面应用 | 独立实例 GPU 路径与窗口短测通过；不代表在线服务内容验收 |
| Trae CN | 独立实例欢迎页与 GPU 短测通过；附精确条件的一次启动容错 |
| CC Switch | WebKit 实际硬件策略、Mali 与窗口短测通过；使用 SHM 传输 |
| 候选框/菜单 | 已有 X11 裁剪补丁在作者设备有验证；更换组件后仍需回归 |
| sRGB、更高 OpenGL 特性、视频硬解 | 尚未覆盖或接通 |
| 长时间稳定、休眠恢复、续航改善 | 尚未完成新版系统性验收 |

## 构建与部署

桥接构建读取 [sources.lock.json](sources.lock.json)，安装器只写独立前缀，不自动覆盖现有栈：

```sh
bash scripts/build.sh --prefix /opt/pad7spro-gpu --jobs 4
bash scripts/install.sh "$(cat build/last-stage.txt)" /opt/pad7spro-gpu
```

依赖安装、挂载条件、入口链接和设备迁移步骤见 [复现流程](docs/setup.md)及 [构建说明](docs/build.md)。`activate-desktop.py` 是作者设备的已知入口迁移工具，不能当作任意 rootfs 的全新安装器。

当前 Termux:X11 从固定提交及子模块干净构建，已部署至 0014，配合 WSI 0012；签名、完整哈希、两端映射与最终测试见[验收证据](evidence/deferred-copy-wake-2026-10-17.json)。本次为作者设备的 r3.5 定版及本地归档，不代表通用公开二进制包或其他设备已验证。

## 文档

- [架构与数据路径](docs/architecture.md)
- [实现机制与流程](docs/implementation.md)
- [复现与安装顺序](docs/setup.md)
- [固定依赖构建](docs/build.md)
- [默认环境、应用与桌面启动](docs/configuration.md)
- [验证方法](docs/validation.md) / [当前状态](docs/development-status.md)
- [性能、功耗与稳定性测量](docs/benchmarks.md)
- [已知问题](docs/known-issues.md)
- [上游来源](THIRD_PARTY.md) / [许可证](LICENSE-STATUS.md)

报告问题请附设备/软件版本、所选入口、实际 renderer、对应 GPU PID/模块、复现步骤和结果。公开日志前移除账号、令牌和个人内容。不要用单次 FPS、持有 `/dev/mali0` 或“窗口能打开”代替硬件渲染、画面和功耗验证。
