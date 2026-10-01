# 当前验证状态

日期：2026-10-01。开发版核心构建与运行探针已通过，完整桌面发行验收仍在进行。

## 已验证

- 固定三个上游 revision、完整 libhybris/WSI 补丁及修改版 libc 哈希。
- 干净构建真实退出码为 0；构建前验证补丁后的关键源码哈希及分配器钩子策略。
- 修复后新构建产物的 Vulkan 初始化、Mali-G925 识别和实例销毁连续三次通过。
- 同一新产物的 AHardwareBuffer 分配、Unix socket 传输和释放连续三次通过。
- `scripts/android-probe.sh` 同时完成两个探针，输出 `GPU_CORE_PROBES_OK`。
- 提供统一 `gpu-run` 入口；`gpu-run probe` 已验证。GUI 子命令仍需实际窗口测试。

## 已修复的问题

清理 canary 诊断代码时，补丁生成误匹配函数声明并恢复了上游分配器钩子，导致 Android 分配的内存被 glibc 释放。恢复工作设备已移除的分配器相关钩子后，非法指针退出问题消失。构建现在同时检查关键源码 SHA-256 与钩子策略，防止遗漏。

AHardwareBuffer 还要求在 chroot 中显式绑定 Android 原有 binderfs。仅 rbind `/dev` 可能被既有子挂载遮挡，出现 `/dev/binder` 无法打开；显式绑定后连续三次测试通过。不能在 chroot 新建 binderfs 实例。

Vulkan 识别阶段仍可能输出 Android 库的探测提示。这里的通过依据是目标硬件识别、真实退出码及随后成功的 AHB 调用，不是忽略错误后宣称成功。

## 尚未完成

- 新栈的 X11/Chromium 实际画面、输入法候选框和菜单回归。
- 修补版 Termux:X11 在明确工具链上的干净重建及升级/签名说明。
- 自动升级、回退和卸载；当前安装器拒绝覆盖已有前缀。
- 当前 60 FPS 配置下的长时稳定、休眠恢复与同条件功耗测试。
- 完整干净 rootfs 的端到端安装验收和正式 `v0.1.0` 发行。

现有 `/opt/mali-bridge` 与 canary 日常环境没有切换到新栈。新前缀 `/opt/pad7spro-gpu` 供独立开发验证。
