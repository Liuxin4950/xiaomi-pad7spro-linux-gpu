# 上游组件与来源

运行基线已更新为 r3.3，见 [CURRENT-STATE](docs/CURRENT-STATE.md)。本文的发布/许可约束仍适用，不以实机部署替代许可或完整发行验收。

更新日期：2026-10-07。当前构建基线、补丁及下载哈希以 [sources.lock.json](sources.lock.json) 为准。本次公开的是源码开发更新，不是已经完成全部验收的 `v0.1.0` 二进制发行。

Linux 桥接组件已锁定完整上游提交，并保存本仓库使用的完整补丁。sysvk/AHB 使用本项目按公开接口重新编写的 MIT 实现。修改版 bionic 仍通过固定 URL 与 SHA-256 获取；这不等于已经完成其对应源码重建。

| 组件 | 当前源码或运行依赖 | 许可证证据与边界 | 仍需补齐 |
|---|---|---|---|
| Termux:X11 | [termux/termux-x11](https://github.com/termux/termux-x11)，基线 `d55f1b7e575de0a7d2b03c5882d5e3d375d01a4f`；两个补丁已锁定 | 固定提交的 LICENSE 为 GNU GPL v3；依赖子模块各自保留许可证 | 干净全量 APK 重建、对应源码与工具链发行记录；现有候选只是原生增量重打包 |
| Vulkan WSI layer | [xMeM/vulkan-wsi-layer](https://github.com/xMeM/vulkan-wsi-layer)，`d5624d42d8b2debbd910ad25662a05c751eb38b7`；完整补丁位于 `patches/wsi/` | 固定源码 LICENSE 为 MIT，保留 Arm 版权与通知 | 正式二进制发行时随附实际使用版本的许可证与构建记录 |
| libhybris | [Linux-on-droid/libhybris](https://github.com/Linux-on-droid/libhybris)，`29e0fa6da0166261f6b9437582fe2d56bab8530c`；完整补丁位于 `patches/libhybris/` | 固定源码含 LGPL-2.1、Apache-2.0、BSD、MIT 等文件级许可；许可证文本已收录于 `patches/libhybris/licenses/` | 按发行内容继续核对文件级版权、通知及对应源码，不能用单一包声明覆盖全部文件 |
| Android headers | [Linux-on-droid/android-headers-30](https://github.com/Linux-on-droid/android-headers-30)，`a6261c5cce8e945868b68318e867e382dea4bffd` | 使用固定源码，保留各头文件的原有许可 | 随实际发行内容整理许可证与通知 |
| sysvk | 本项目 [src/sysvk.c](src/sysvk.c)，按公开 Android Vulkan HAL 接口编写；由本仓库 CMake 构建 | 文件 SPDX 与顶层 LICENSE 为 MIT | 随正式发行记录本仓库提交和对应产物哈希 |
| AHB wrapper | 本项目 [src/ahb-wrapper.c](src/ahb-wrapper.c)、[src/ahb-api.h](src/ahb-api.h)，通过 libhybris 解析公开 AHardwareBuffer 接口 | 文件 SPDX 与顶层 LICENSE 为 MIT | 随正式发行记录本仓库提交和对应产物哈希 |
| AOSP Vulkan HAL 头文件 | [vendor/aosp/hardware/hwvulkan.h](vendor/aosp/hardware/hwvulkan.h) | 保留 AOSP 版权头与 [Apache-2.0 许可证](vendor/aosp/LICENSE.Apache2) | 正式发行继续保留该通知 |
| 修改版 bionic libc | [固定 vendor_lindroid 文件](https://github.com/Linux-on-droid/vendor_lindroid/blob/eadbb70f13209133d96a5355464388db8c6578de/prebuilt/arm64/libc.so)；SHA-256 在锁文件中，已与设备工作文件核对 | 上游预编译运行时依赖；固定文件与哈希不能替代对应源码、修改内容和许可核对 | 对应 bionic 源码 revision、emutls 修改、完整重建步骤及二进制再分发范围 |
| Mesa / ANGLE / Vulkan loader | Debian 包与目标应用携带的组件 | 各自上游及发行包许可 | 记录实际版本与构建来源；不随意重发整个应用包 |
| Android Mali Vulkan 驱动 | 用户自己的 Android 固件 `/vendor` 等路径 | 厂商组件，未确定再分发授权 | 作为设备运行依赖，不打包为项目源码 |

历史研究参考过 [xMeM/sysvk](https://github.com/xMeM/sysvk) 和 [kde-yyds/android-vulkan-bridge](https://github.com/kde-yyds/android-vulkan-bridge) 的包配方。旧说明中的 sysvk `unknown`、AHB 包 `GPL2` 等描述属于这些历史来源，不能作为本仓库重写实现的许可说明，也不能反过来用本仓库 MIT 声明覆盖旧实现或配方。

当前入口使用本项目 **sysvk ICD**，不是把参考配方涉及的所有 wrapper 都加入运行链。软件实际版本、窗口验证及尚未完成的功耗和兼容性工作见 [当前状态](docs/development-status.md)；来源可追溯、许可整理和功能验收是不同事项。
