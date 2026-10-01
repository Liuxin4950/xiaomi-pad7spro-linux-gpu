# 从固定源码构建

构建入口为 `scripts/build.sh`。完整构建和独立安装已通过，修复后的 Vulkan/AHB 探针也已通过，但尚不能标记为完成整套桌面复现。见 [验证状态](development-status.md)。

## 构建环境

在 Debian arm64 chroot 内构建；Android root 只用于进入容器和后续访问驱动。先安装构建依赖：

```sh
apt-get update
apt-get install -y python3 git build-essential cmake autoconf automake libtool pkg-config \
  libglvnd-dev libvulkan-dev libx11-dev libx11-xcb-dev libdrm-dev \
  libxcb1-dev libxcb-dri3-dev libxcb-present-dev libxcb-sync-dev libxcb-xfixes0-dev
```

构建脚本清除 Android 的 `LD_PRELOAD`/`LD_LIBRARY_PATH`，使用 Linux PATH、`TMPDIR=/tmp` 和明确的 `aarch64-linux-gnu` build triplet。它不会使用作者之前安装的 `/opt/mali-bridge` 或 canary 库。

## 运行

在项目目录执行：

```sh
bash scripts/build.sh --prefix /opt/pad7spro-gpu --jobs 4
```

需要调整缓存/构建位置时使用 `--work /absolute/path`。安装前缀必须是 `/opt` 下的专用单级目录。每次编译使用新的隔离工作目录，源码缓存与编译产物分开。

脚本先按 [sources.lock.json](../sources.lock.json) 获取三个精确 Git revision，核对并应用项目补丁，再校验修改版 libc 的 SHA-256。所有构建阶段必须成功，最终才输出 `BUILD_OK`。构建过程只写入工作目录中的 stage，**不会自动覆盖现有安装**。

成功后的 stage 路径保存于 `build/last-stage.txt`（或自定义工作目录下的同名文件）。后续安装器需要验证该 stage 的文件清单与依赖，再写入对应前缀。

## 项目与外部依赖的范围

- `src/sysvk.c`、`src/ahb-wrapper.c` 是本项目按公开 Vulkan HAL/AHardwareBuffer 接口编写的桥接组件，采用 MIT。
- libhybris / WSI 从固定上游 revision 构建，保留上游许可证并应用完整补丁。
- Android headers 从固定源码仓库安装，保留文件级许可。
- 修改版 bionic 是固定上游 URL 加 SHA-256 的运行时依赖，下载内容已与工作设备逐字节哈希对应。当前流程没有从 Android 整体源码重建它；这项范围限制必须公开说明。
- Android 原厂 Mali 驱动仍由用户自己的固件提供，不包含在项目源代码中。

## 验证要求

补丁能应用、源码能编译、Vulkan 能识别 GPU、X11 呈现正确和实际应用稳定，是不同的检查。构建通过后依然要测试独立安装、应用渲染、60 FPS 和功耗，不能用 `BUILD_OK` 代替后续验收。

## 独立开发安装

```sh
bash scripts/install.sh "$(cat build/last-stage.txt)"
```

安装器不会覆盖已有前缀。当前供独立开发验证，完整窗口回归完成前保留日常工作入口。
