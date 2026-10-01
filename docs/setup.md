# 复现流程与当前缺口

本文给出首版需要完成的复现顺序。标有“待完成”的部分没有可供照做的完整步骤；当前草稿不能用于从零安装整套桥接。

## 前置条件

- 已取得 root 的 Xiaomi Pad 7S Pro，系统版本见主 README。
- Termux、配套 Termux:X11 Android APK 与 Termux 侧 loader/package。
- Debian arm64 chroot 与 XFCE。参考 rootfs 路径为 `/data/linux/debian`。
- 可访问 Mali 节点和 Android 既有 binderfs，并能在桌面所在挂载命名空间绑定 Android 文件系统。
- 保存当前桌面工作后再做安装、停止或更换 APK；停止脚本会终止该 chroot 内的工作进程。

现有启动器以 root 运行应用，Chromium/Electron 使用 `--no-sandbox --disable-gpu-sandbox`。这是当前已部署配置的限制；发行时应明确说明，后续普通用户和 sandbox 支持需另行适配。

本机读取时 Android SELinux 为 `Enforcing`；本轮未审计全部既有策略，不能由此保证新机器直接可用。不要将关闭 SELinux 当作已经验证的安装必需条件。

## 构建与安装的顺序

1. **锁定依赖（待完成）**：提供 libhybris、sysvk、AHB wrapper、WSI、Android headers 和修改版 bionic libc 的精确上游 revision、完整补丁、许可证及工具链版本。来源线索见 [THIRD_PARTY.md](../THIRD_PARTY.md)。
2. **干净构建桥接（待完成）**：在独立构建目录编译，完整记录配置和依赖；任何阶段失败应非零退出。现有旧脚本会把部分失败转换为 `STAGE_FAILED` 输出，不能原样当作正式发行构建入口。
3. **检查库和 loader（待完成）**：核对 ICD JSON 指向的库、WSI layer JSON、动态依赖和 RUNPATH；历史 RPATH 修复脚本只处理部分路径，不能以“执行过脚本”代替 `readelf` 验证。
4. **构建修补版 Termux:X11**：按 [补丁说明](../patches/termux-x11/README.md)使用固定提交。此补丁已经过应用检查；本轮未从零重建 APK。
5. **部署至独立前缀（待完成）**：先保留工作配置，定义安装文件清单和回退步骤；不要在现有桌面会话中替换正在使用的库。
6. **配置桌面和应用入口**：参考 [配置说明](configuration.md)。默认 60 FPS，保留原生分辨率；先验证 Chromium，再逐个接入其他应用。
7. **验证并记录**：按 [GPU 验证](validation.md)完成正确性检查，再按 [测试计划](benchmarks.md)测量功耗和稳定性。

## 回退要求

正式安装器需要记录写入的库、脚本、桌面入口和 APK 版本，能够只恢复本次变更。当前参考停止脚本负责结束整个 Debian 环境，不是卸载器。

修改前的备份可保存在电脑。设备上不堆放实验备份；恢复时使用经过核对的固定文件和哈希。不要用全局进程清理代替应用级回退，也不要尝试在运行中的 mount namespace 强行换挂载。

## 首版验收

- 干净的同机型环境按文档从源码/明确来源安装成功，过程不依赖作者已有 `/opt` 文件。
- 所有发布产物可追溯到源码、补丁、构建版本和哈希。
- 启动、GPU 渲染、输入法/菜单遮挡、停止与回退均有记录。
- 60 FPS 实际生效，且功耗对照条件一致。
- 已知失败、尚未支持的应用与功能公开列出。
