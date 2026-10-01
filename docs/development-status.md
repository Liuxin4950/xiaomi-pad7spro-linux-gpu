# 当前验证状态

日期：2026-10-01。此记录区分既有工作环境与新发行构建。

## 已通过

- 三个固定 Git revision、两个完整补丁、上游 libc SHA-256 核对。
- 从固定源码构建 libhybris、独立 sysvk/AHB wrapper、Vulkan 探针及 WSI，完整构建真实退出码为 0。
- 在独立 `/opt/pad7spro-gpu` 安装，未替换作者的 `/opt/mali-bridge` 或 canary 环境。
- Termux:X11 补丁对固定上游提交的应用检查。

## 尚未通过

新栈探针可输出 `Mali-G925-Immortalis`、vendor `0x13b5`、Vulkan `1.3.278`，但销毁实例时发生 glibc `free(): invalid pointer`，真实退出码为 `134`。

对照结果：同一探针使用既有 stable/canary 库时正常退出；新栈禁用 WSI 后仍失败；替换为既有 canary libhybris 后通过。问题范围缩小到新构建的 libhybris。仅恢复原 `--enable-debug --enable-trace` 配置尚未解决问题。根因未确认，不能把这些对照当作修复。

继续比较原二进制的实际分配器 hook 与新构建，定位 Android 与 glibc 分配/释放的边界。确认修复后再重跑完整构建、探针、X11/Chromium 和日常启动测试。

## 后续验收

安装、升级/回退、修补 APK 干净重建、60 FPS 的真实会话、中文输入候选框与菜单、长时稳定性和同条件功耗测试仍需完成。这是开发版，不是已验收的一键发行版。
