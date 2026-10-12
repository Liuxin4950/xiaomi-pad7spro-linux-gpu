# 配置、启动和停止

当前唯一基线和重启状态见 [CURRENT-STATE](CURRENT-STATE.md)。

更新：2026-10-12。本文描述当前作者设备的已部署入口；构建、安装和首次接入步骤见 [复现流程](setup.md)。

## 当前路径与日常启动

当前完整桥接安装在 `/opt/pad7spro-gpu-observe-20261012`。`/usr/local/bin/gpu-run`、`/usr/local/bin/gpu-launcher` 分别链接到该目录的 `bin/gpu-run`、`bin/gpu-launcher`。ICD、libhybris、AHB、WSI、修改版 bionic 和应用适配组件都取自同一前缀；旧主基线/canary 不再是默认运行依赖。

| 入口 | 所在环境 | 作用 |
|---|---|---|
| Termux Widget 的 `debian-zink.sh` | Termux | 调用 `~/mali-work/desktop-zink.sh`，启动或复用桌面 |
| `~/mali-work/desktop-zink.sh` | Termux | 复用 `~/debian-shell.sh` 的挂载、会话和看门狗逻辑，准备 Android 资源并启动 X11/XFCE |
| `/usr/local/bin/gpu-run` | Debian | 统一前置检查、完整前缀选择和应用渲染路由 |
| `/usr/local/bin/gpu-launcher` | Debian | 可选的程序输入框，不是运行普通应用的必经入口 |
| `~/debian-stop.sh` | Termux | 保存工作后停止该 chroot 的全部进程并清理挂载 |

实际 Termux 脚本已部署；用户已关闭旧会话并从 Widget 重启，确认启动成功。重启后读取到的 Termux:X11 命令含 `:1 -ac -dpi 120 -max-fps 60`。再次点击仍在运行的桌面只会复用现有会话，不热替换已加载的库。

在 Termux 手动启动的等价命令：

```sh
bash ~/mali-work/desktop-zink.sh
```

桌面会话通过 `gpu-run gl /usr/bin/env LANG=zh_CN.UTF-8 dbus-launch --exit-with-session startxfce4` 继承统一 GPU 环境。普通 Mesa/OpenGL、Vulkan 程序可从桌面或终端正常启动，不必全部经过输入框；需要框架专用参数或策略的应用使用对应入口。

当前桌面保留 Chromium、ChatGPT、Trae CN、CC Switch、Office 与 MySQL 图标。GPU 应用和 Office 图标与已迁移的系统菜单/URL 入口使用 `/usr/local/bin/gpu-run`；GPU 输入框没有保留在桌面。MySQL 入口调用 `/root/.local/libexec/liutech/start-mysql.sh`，与 GPU 桥接独立。

在已经运行的 Debian 桌面中，也可执行：

```sh
gpu-run chromium
gpu-run chatgpt
gpu-run trae
gpu-run cc-switch
```

旧 `/opt/mali-bridge-canary/bin/gpu-app.sh` 仅保留为转发到 `/usr/local/bin/gpu-run` 的兼容脚本，不再设置旧库路径。不要在应用图标中重复追加 ANGLE 参数或 preload。

## 应用类型与通用入口

| 应用类型 | 入口 | 行为与边界 |
|---|---|---|
| Chromium、Electron | `gpu-run auto BINARY`；已知应用可用 `chromium/chatgpt/trae` 别名 | 二维原生 Skia Vulkan + WebGL ANGLE Vulkan；保留应用用户配置，root 下采用当前无 sandbox 配置 |
| 原生 OpenGL/Mesa | `gpu-run gl BINARY` 或继承桌面环境直接启动 | Zink → Vulkan；不注入浏览器参数 |
| 原生 Vulkan | `gpu-run vulkan BINARY` 或继承桌面环境直接启动 | 当前前缀的 ICD + X11 WSI |
| WebKitGTK/Tauri | CC Switch 用 `gpu-run cc-switch`；其他明确的 WebKit 应用用 `gpu-run webkit BINARY` | 单独的 WebKit 合成策略与 SHM 传输适配，不套用 Electron 参数 |

`auto` 识别 Chromium/Chrome、Electron 数字版本名、ChatGPT、Trae，也检查符号链接实际目标。对重命名 Electron，执行文件旁须同时有 `icudtl.dat` 与 `resources/app.asar` 或 `resources/app/package.json` 才添加 ANGLE 参数；普通 `resources` 目录不足以判定框架。无法识别的程序只接收标准硬件环境。`gpu-run electron BINARY` 可显式选择 Electron 路径。

新软件通常可先直接启动或用 `gpu-run auto BINARY`；只有框架自行禁用合成、采用其他窗口后端或要求驱动缺失功能时，才需要单独适配。AppImage、容器内应用以及自行改写图形环境的程序要核对实际执行文件和 renderer，不能承诺所有新软件自动兼容。

CC Switch 的硬件入口保留 WebKit 加速合成、强制 SHM 传输，并通过 `libwebkit-gpu-policy.so` 纠正应用主动关闭硬件加速的真实策略 setter。Chromium/Electron 不加载这个适配库。显式 `webkit` 是针对已确认框架的选择，不是对任意原生程序的通用 preload。WebKitGTK WebGL2 尚不在本机已验证范围。

Trae 使用 `bin/trae-start`：只在启动最初 8 秒遇到精确 Oilpan cage 地址预留失败、确认 profile 无存活/不明单实例持有者，且没有 GPU、renderer、utility、JS 初始化或日志/GPU 缓存进展标记时，最多重新启动一次。正常运行不周期扫描进程；其他错误不自动重启，重复失败返回非零。这是受限地址空间下的启动容错，不是 GPU 修复，不改用户 profile、V8 内存参数或 ASLR 设置。

## 前缀、颜色和帧率

安装入口从自身真实路径推导前缀。`PAD_GPU_PREFIX` 可显式覆盖；前缀必须是 `/opt` 下的专用单级目录，不能是 `/opt/.` 或 `/opt/..`。直接运行仓库中的 `scripts/gpu-run.sh` 时，未指定该变量会选择默认 `/opt/pad7spro-gpu`，不会自动跟随系统链接；检查当前日常栈优先用 `/usr/local/bin/gpu-run`。

| 配置 | 当前默认 | 说明 |
|---|---|---|
| Rootfs | `/data/linux/debian` | 当前 Termux 共享脚本的配置 |
| Display | `:1` | `DEBIAN_DISPLAY=:N` 可选择本机显示号；另一个 display 不保证隔离 APK renderer |
| X11 DPI | `120` | `X11_DPI` 可覆盖，与 Android 系统 DPI 不等同 |
| `X11_MAX_FPS` | `60` | Termux 启动参数，允许 1–240，只在新建 X server 时生效 |
| `PAD_GPU_SKIA_BACKEND` | `native` | Chromium/Electron 二维后端；`angle` 是硬件回退 |
| `PAD_GPU_MAX_FPS` | `60` | 每个 WSI 交换链的提交上限；允许 1–240，0 关闭此上限 |
| `PAD_GPU_X11_COLOR_MODE` | `bgra` | 当前 Termux:X11 使用的统一字节契约 |
| `HYBRIS_VULKANPLATFORM` | `null` | 避免选择未配置的 Wayland 平台 |

当前显示链路使用 Xorg BGRA 字节契约。WSI 公开真实 BGRA 渲染格式，以 GPU 复制字节到私有 RGBA gralloc AHB，避免显示端再次交换通道。`native` 保留给开发验证，未经配套改造的当前 APK 不应使用；sRGB 交换链暂不宣称支持。

应用级限帧使用可被关闭事件唤醒的等待，降低持续提交频率，不做内容去重，不能说静止窗口已停止渲染。X11 与应用级上限现均为 60，长期功耗和双重节拍的延迟仍需同条件测量。会话移除了旧 `vblank_mode=0`，不伪装 OpenGL 版本。Mesa/Zink 基线曾报告 Mali 硬件 OpenGL 3.2，同时提示缺少 `fillModeNonSolid`、`shaderClipDistance`；高版本功能仍以真实驱动能力为准。

当前 APK 已更新：原生 Copy 批处理和输入接口修正已在前端运行；X server 已正常重开并加载显示 tick 更新；后续升级同样需要重开。详见 CURRENT-STATE。

## 显式软件模式与诊断

硬件入口失败时返回非零，不自动改用 CPU。需要软件渲染时显式选择：

```sh
gpu-run --software auto /usr/lib/chromium/chromium --user-data-dir=/tmp/chromium-cpu-test
gpu-run --software cc-switch
```

已识别 Chromium/Electron 使用禁用 GPU 的参数；标准 Mesa OpenGL 使用 llvmpipe；Vulkan 选择系统 lavapipe ICD，显式 `vulkan` 模式缺少 lavapipe 会报错。WebKit 软件模式关闭合成，不加载硬件策略库。自行绕过标准接口的程序仍需确认实际路径。

```sh
gpu-run doctor
gpu-run info
gpu-run info 目标GPU进程PID
gpu-run probe
gpu-run ahb
gpu-run --headless vulkan vulkaninfo --summary
```

`doctor` 检查组件/JSON、Android 资源、X11 连通性并列出动态依赖，不创建 Vulkan 设备。`info` 不带 PID 仅输出配置，带 PID 才读取实际模块。`probe` 验证设备提交与读回，`ahb` 验证分配、传输、读回和释放；它们不能代替窗口、输入法、菜单和长期稳定性验收。`--headless` 仅跳过窗口前置检查，不替应用添加 headless 参数。

启动器清理继承的旧 preload、库搜索路径、Vulkan、hybris 和 Mesa 图形变量，再设置选中栈，保留应用和会话设置。诊断所需运行组件为 `python3`、`x11-utils`、`coreutils`；可选输入框还需要 `zenity`。输入框按参数数组启动程序，不执行 shell，日志存于 `~/.local/state/pad-gpu/launches/`。直接启动应用时另收集 stderr；兼容脚本的 `/tmp/mali-gpu-launch.log` 不包含完整应用日志。

独立 Chromium/Electron 验证应使用全新 `--user-data-dir`，避免命令交给已运行实例。它仍共享当前 X server、APK renderer 和物理 GPU。AHB 内容优先用 Android 截图或实际观察验收。低开销采样可用 `scripts/sample-gpu.py --pid GPU_PID --seconds 10 --output /absolute/path/sample.csv`；传感器为整机数据，不能独立证明某应用功耗。

保存工作后，在 Termux 停止整个环境：

```sh
bash ~/debian-stop.sh
```

普通 `~/debian-desktop.sh` 与 zink Widget 共用当前 GPU 桌面。CLI 别名和 `/usr/bin/chatgpt` 的已知发行版 shell 入口也转发 gpu-run；直接 ELF 是开发接口。历史诊断脚本不是日常启动方式。
