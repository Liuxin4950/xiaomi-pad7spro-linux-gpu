# 架构与组件

## 渲染与呈现

Linux 应用在 glibc 用户空间运行；Android 厂商 Vulkan 驱动依赖 bionic。libhybris 负责装载/兼容 Android 用户空间库，sysvk 向 Linux Vulkan loader 暴露 ICD 入口。OpenGL 应用可经 Mesa Zink 转成 Vulkan；Chromium/Electron 当前使用 ANGLE Vulkan。

Android 驱动本身没有直接提供这里需要的标准 Linux X11 呈现环境。WSI 层与 AHardwareBuffer wrapper 配合，向 Termux:X11 交付可呈现的 buffer。Termux:X11 的 GPU Present 快速路径最终与 Android 显示链路协作。

这三层应分别验证：应用是否使用 GPU 渲染、X11 呈现是否正确、Android 是否完成显示。XFCE 面板和窗口边框的绘制不等于 Chromium 内容的渲染。本配置关闭 XFWM 合成器，不能据此推断所有桌面组件都使用 GPU。

## 当前路径布局

| 路径 | 用途 |
|---|---|
| `/opt/mali-bridge/lib/libsysvk.so` | 主基线 Vulkan ICD |
| `/opt/mali-bridge/share/vulkan/icd.d/sysvk_icd.json` | ICD 描述 |
| `/opt/mali-bridge/lib/libahb-wrapper.so` | AHardwareBuffer 包装 |
| `/opt/mali-bridge/android-override/libc.so` | 桥接专用的修改版 bionic libc |
| `/opt/mali-bridge-canary/lib` | 当前应用入口使用的 libhybris 候选库 |
| `/opt/mali-bridge-canary/share/vulkan/implicit_layer.d` | 当前应用入口使用的候选 WSI |
| `/opt/mali-bridge-canary/bin/gpu-app.sh` | Chromium / ChatGPT / Trae 的统一入口 |

“canary”是历史目录名，目前生产应用入口也依赖它。不能仅复制 canary 就宣称依赖齐全：启动器同时使用主基线的 ICD、AHB wrapper 和 Android override。正式发行时应提供一个明确版本的完整组件清单，再决定是否统一安装前缀。

## 必要的适配

- **Android binderfs**：绑定 Android 现有 `/dev/binderfs`；在 chroot 中创建新的 binderfs 实例会缺少 Android 服务环境。`binder_logs` 是本机识别既有实例的辅助标志，不能假设所有固件都采用相同目录布局。
- **Android 文件系统**：当前启动器绑定 `/system`、`/vendor`、`/apex`，并共享设备节点与 X11 socket。取得 root 本身不证明所有节点都可访问，还涉及挂载命名空间与 SELinux 策略。
- **修改版 bionic libc**：通过 `HYBRIS_LD_LIBRARY_PATH` 优先选择私有 override。不要改写宿主 Android 的 `/apex/.../libc.so`。对应 emutls 源码和构建还需整理。
- **libhybris 与 WSI 修正**：历史记录包含链接器初始化、DSO 生命周期和 X11 swapchain 空图像检查修正；正式补丁系列需从实际部署源码重建，不能只取旧电脑源码的部分 diff。
- **Termux:X11 修正**：直接写入 screen pixmap 时应用可见区域裁剪，保留 redirected pixmap 的内容语义；加入真实 vblank 限帧，并关闭非调试模式下的逐帧日志。

## 依赖说明

此方案使用用户固件自带的 Android Mali 驱动，不是实现了一个新的 Mali 内核驱动，也不代表厂商驱动已开源。对不同固件、Android 用户空间库、GPU 功能和 Termux:X11 协议版本的兼容性都需要验证。
