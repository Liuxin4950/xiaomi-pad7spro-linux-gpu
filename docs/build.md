# 从固定源码构建

更新：2026-10-07。构建入口为 `scripts/build.sh`，安装入口为 `scripts/install.sh`。作者设备已部署完整前缀 `/opt/pad7spro-gpu-dev-20261007-r2`，并完成核心探针、真实呈现及应用短验收；构建成功仍不等同于所有应用或长期功耗达标。

## 环境与依赖

在 Debian arm64 chroot 内构建，先准备依赖：

```sh
apt-get update
apt-get install -y python3 git build-essential cmake autoconf automake libtool pkg-config \
  libglvnd-dev libvulkan-dev libx11-dev libx11-xcb-dev libdrm-dev \
  libxcb1-dev libxcb-dri3-dev libxcb-present-dev libxcb-sync-dev libxcb-xfixes0-dev
```

运行/诊断还需要系统 Mesa/Zink 和 Linux Vulkan loader；可选程序输入框使用 `zenity`，作者设备入口迁移使用 `desktop-file-utils`：

```sh
apt-get install -y libvulkan1 mesa-vulkan-drivers libgl1-mesa-dri \
  x11-utils coreutils zenity desktop-file-utils
```

应用本体及其 WebKitGTK 等依赖由应用安装渠道提供。

构建脚本使用 Linux PATH、`TMPDIR=/tmp`、明确的 `aarch64-linux-gnu` triplet，并清除继承的 preload/库搜索路径。它不使用作者旧主基线或 canary 目录。Android 原厂驱动通过运行时挂载提供，不复制到构建源码中。

## 固定依赖与隔离构建

在仓库中选择尚不存在的安装前缀：

```sh
bridge_prefix=/opt/pad7spro-gpu-next
bash scripts/build.sh --prefix "$bridge_prefix" --jobs 4
```

`--work /absolute/path` 可改变缓存/构建位置。前缀必须是 `/opt` 下的专用单级目录，排除 `.`、`..`；构建与安装必须使用同一前缀，因为 ICD 和动态库 RUNPATH 写入该路径。需要更换前缀时重新构建，不直接搬动已经构建好的安装目录。

`sources.lock.json` 固定 libhybris、WSI、Android headers 的 Git revision、项目补丁及关键修改文件哈希，同时固定修改版 bionic 的下载 URL 和 SHA-256。源码缓存位于 `build/sources`；每次构建在 `build/runs/build.*` 中导出独立源码并生成 stage，已有完整缓存可复用。

构建会检查 libhybris hook 的分配器边界，编译 sysvk、AHB wrapper、WSI、WebKit 策略组件和探针，安装通用入口/Trae 包装。stage 中移除 libhybris 的 Vulkan loader shim 及依赖它的测试产物，保留系统 Linux Vulkan loader；不能让它重新覆盖 `libvulkan.so`。

所有阶段成功后才输出 `BUILD_OK`。最终 stage 路径写入 `build/last-stage.txt`，或自定义工作目录的同名文件。构建只写工作目录，不覆盖已有安装或修改日常桌面入口。

## 安装完整前缀

```sh
bash scripts/install.sh "$(cat build/last-stage.txt)" "$bridge_prefix"
```

安装器检查核心库、WSI、ICD、bionic、WebKit 适配、三个探针以及 `gpu-run`、`gpu-launcher`、`trae-start`；检查 JSON/前缀，生成 SHA-256 文件清单和符号链接清单，拒绝越出树的符号链接。目标已存在时返回非零；成功后输出 `INSTALL_OK`。

| 安装内容 | 作用 |
|---|---|
| `lib/libsysvk.so`、libhybris/linker、`libhardware` | Linux Vulkan ICD → Android HAL/驱动 |
| `lib/libahb-wrapper.so*`、`android-override/libc.so` | AHB 公共 ABI 包装与固定 bionic 运行依赖 |
| `share/vulkan/icd.d/`、`share/vulkan/implicit_layer.d/` | 当前前缀的 ICD/WSI JSON 和呈现层 |
| `lib/libwebkit-gpu-policy.so` | 明确的 WebKit/CC Switch 硬件策略适配 |
| `bin/gpu-run`、`bin/gpu-launcher`、`bin/trae-start` | 通用命令、可选输入框、有限 Trae 启动容错 |
| `bin/probe-vulkan`、`bin/probe-ahb`、`bin/probe-present` | 设备提交/读回、AHB 往返、真实窗口呈现回归 |
| `sources.lock.json`、`install-manifest.json` | 依赖来源和安装文件清单 |

核心组件都在一个前缀内；当前实例不依赖旧 canary 库。基础安装不会创建系统链接、改应用图标或部署 APK。安装后先直接运行候选 `bin/gpu-run doctor/probe/ahb` 并完成实际呈现/应用验证，再按 [接入流程](setup.md)切换系统链接和迁移已有桌面。

## 源码与产物范围

- `src/` 下的桥接、策略和探针组件由本项目提供；许可证范围见项目对应文件及许可证说明。
- libhybris、WSI 和 Android headers 按固定上游源码构建，保留其许可证并应用项目补丁。
- 修改版 bionic 是固定上游二进制运行依赖，当前流程没有从 Android 整体源码重建它；不能声称全部依赖均在本仓库从源码生成。
- Android 原厂 Mali 驱动仍由用户固件提供，不包含在项目发布源码中。
- `patches/termux-x11/` 单独管理显示端补丁。桥接构建不会重建、签名或安装 APK；当前设备没有升级候选 `0002`。

补丁可应用、构建/安装成功、GPU 设备提交成功、窗口像素正确和长期应用稳定是不同结论。更多验收范围见 [验证状态](development-status.md)、[验证方法](validation.md)和[功耗计划](benchmarks.md)。
