# 上游组件与来源

当前构建版本以 [sources.lock.json](sources.lock.json) 为准。构建使用本项目 MIT 的 sysvk/AHB 源码，旧来源项只保留历史线索。固定上游 libc 下载的 SHA-256 与设备工作版本一致；完整 Android 源码重建尚未完成。

此表区分“打包/文档提供的来源线索”和“已确定的实际源码基线”。缺少精确 revision 的组件仍需在发布前对齐，不能直接将当前上游 HEAD 当作已安装版本。

| 组件 | 来源证据/链接 | 当前许可证证据 | 待补齐 |
|---|---|---|---|
| Termux:X11 | [termux/termux-x11](https://github.com/termux/termux-x11)，基线 `d55f1b7e575de0a7d2b03c5882d5e3d375d01a4f` | 固定提交的 LICENSE 为 GNU GPL v3；依赖子模块各自保留许可证 | 干净重建与对应源码发布 |
| Vulkan WSI layer | Android bridge PKGBUILD 指向 [xMeM/vulkan-wsi-layer](https://github.com/xMeM/vulkan-wsi-layer) | 本地 LICENSE 明示 MIT，Arm 版权 | 实际 fork/revision、完整改动 |
| libhybris | Android bridge PKGBUILD 指向 [Linux-on-droid/libhybris](https://github.com/Linux-on-droid/libhybris) | 包声明 LGPL-2.1；源码包含 Apache-2.0、BSD、MIT 等多种文件级许可 | 精确基线和逐文件版权/许可，不可只用包声明覆盖全部文件 |
| sysvk | PKGBUILD 指向 [xMeM/sysvk](https://github.com/xMeM/sysvk) | 包声明 `unknown`；本地 sysvk.c 未见版权/许可证头 | 明确授权与当前文件来源 |
| AHB wrapper | Android bridge 的 AHB 包声明 [kde-yyds/vulkan-android-bridge](https://github.com/kde-yyds/vulkan-android-bridge) | 包声明 GPL2；本地改造的 ahb-wrapper.c 未见版权/许可证头 | 对齐具体文件来源、原始许可和改造记录 |
| Android Vulkan Bridge 配方 | [kde-yyds/android-vulkan-bridge](https://github.com/kde-yyds/android-vulkan-bridge) | 本地顶层未见 LICENSE；各包各有声明 | 分清配方许可与被构建组件许可 |
| 修改版 bionic libc | 既有说明链接 [vendor_lindroid 的预编译 libc](https://github.com/Linux-on-droid/vendor_lindroid/blob/lindroid-22.1/prebuilt/arm64/libc.so) | 此链接只是预编译来源线索，不能替代对应源码许可审计 | 当前文件哈希/来源、源码 revision、emutls 构建步骤 |
| Mesa / ANGLE / Vulkan loader | Debian 包与目标应用携带的组件 | 各自上游及发行包许可 | 记录实际版本与构建来源；不随意重发整个应用包 |
| Android Mali Vulkan 驱动 | 用户自己的 Android 固件 `/vendor` 等路径 | 厂商组件，未确定再分发授权 | 作为设备运行依赖，不打包为项目源码 |

`android-vulkan-bridge` 还提供 Mesa Vulkan wrapper 配方，但当前日常入口使用 **sysvk ICD**。这些属于来源/参考资料，不能混写成所有组件都同时安装或需要。

本表于 2026-10-01 根据本机源码、PKGBUILD 和设备记录整理。Termux:X11 的固定提交及许可证另经上游页面核对；其余来源线索不构成与实际二进制完全一致的证明。
