# Xiaomi Pad 7S Pro Linux GPU

让已 root 的小米平板 7S Pro 中的 Debian arm64 chroot 图形软件调用 Android 原厂 Mali Vulkan 驱动，并通过 Termux:X11 显示。

当前生产：**r3.5 Linux 栈 + r3.6 输入候选**；已另行构建未切换的 r3.6 Linux 候选。2026-11-11 已整理 r3.6-rc1 的源码、构建与 Termux 接入工具；快速蓝牙鼠标仍有卡顿反馈，正式版验收未完成，不宣称稳定真实 120 FPS 或整机续航提升。

换 Termux 并保留 Debian/rootfs 时，在发布包解压目录运行：

```sh
bash scripts/bootstrap-termux.sh /data/linux/debian
bash ~/debian-desktop.sh
```

bootstrap 安装依赖、写入可配置启动入口并备份原件；不替换 APK、不启动或停止桌面。先保存并正常结束旧桌面，再从新 Termux 启动。该入口以已存在的 GPU rootfs 为前提，不是原厂状态的一键装机。详见 [安装与更换 Termux](docs/setup.md)。

- [唯一当前状态](docs/CURRENT-STATE.md)
- [r3.6 发布候选、代码审查与剩余验收](docs/r3.6-release.md)
- [r3.6 实现路线与可复现交付](docs/r3.6-implementation-plan.md)
- [维护与回退](docs/tablet-handoff.md)

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
run-gpu application              # 通用硬件 GPU 入口；默认 auto 识别应用
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
| Android / HyperOS | 本次回读 Android 17、API 37 / `OS4.0.5.0.XOTCNXM` |
| Linux | Debian 13 arm64、root chroot、XFCE，关闭 XFWM 合成器 |
| Mesa | 25.0.7；Zink 报告 OpenGL 3.2，仍缺部分基础 Vulkan 特性 |
| Termux | `0.118.3` |
| Termux:Widget | `0.15.0`，桌面快捷入口追随统一 gpu-run |
| 当前 Termux:X11 APK | r3.6 鼠标输入候选，`5aed7953…`；server 仍映射旧包，详见 CURRENT-STATE |
| 当前启动默认 | 原生分辨率，`X11_MAX_FPS=120`、`PAD_GPU_MAX_FPS=120` |

设备/系统/APK 身份本轮重新核对；历史应用测试按原日期保留。Termux 配套历史见 [参考资源](reference/README.md)。其他机型、固件、GPU、proot 和非 root/sandbox 配置未验证。

| 应用/能力 | 当前状态 |
|---|---|
| Vulkan / AHB | 逻辑设备、真实指令提交与读回；AHB 发送/接收、读回和释放通过 |
| OpenGL / Zink | 实际齿轮窗口、Mali renderer 和正确 RGB 画面通过 |
| Chromium | ANGLE Vulkan/Mali、WebGL/WebGL2、像素读回与 Android 画面通过 |
| ChatGPT 桌面应用 | 独立实例 GPU 路径与窗口短测通过；不代表在线服务内容验收 |
| Trae CN | 独立实例欢迎页与 GPU 短测通过；附精确条件的一次启动容错 |
| CC Switch | 普通 Zink/Vulkan 硬件入口与实际窗口短测通过；不强制 WebKit preload/SHM 透明策略 |
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

X11 rc1 从固定提交、子模块及 0001–0017 补丁全新构建，未安装；配套 loader 同源构建。Linux WSI 保持 0012。当前包、已运行进程及发布身份分别见 CURRENT-STATE；历史 r3.5 验收见[原始证据](evidence/deferred-copy-wake-2026-10-17.json)。

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
