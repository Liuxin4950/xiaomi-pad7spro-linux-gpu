# 许可证状态

运行基线已更新为 r3.3，见 [CURRENT-STATE](docs/CURRENT-STATE.md)。本文的发布/许可约束仍适用，不以实机部署替代许可或完整发行验收。

更新日期：2026-10-07。本次公开的是当前实现、补丁与文档的源码开发更新；`CMakeLists.txt` 中的 `0.1.0` 是项目版本字段，不表示已经验收并发布正式二进制版本。

顶层 [LICENSE](LICENSE) 使用 MIT，适用于本项目新编写的 `src/`、构建脚本和原创文档，相关源码带有 SPDX 标记。上游源码及其修改、第三方头文件继续保留各自的版权与许可证，不能将它们整体改为 MIT。

`vendor/aosp/hardware/hwvulkan.h` 保留 AOSP 的 Apache-2.0 版权头及同目录下的许可证文件。本次构建的 `src/sysvk.c`、`src/ahb-wrapper.c` 和 `src/ahb-api.h` 是按公开接口重新编写的 MIT 实现，不再使用旧包配方中来源或许可不清晰的包装实现。历史参考资料的包许可不作为这些新文件的许可依据。

Termux:X11 基线采用 GNU GPL v3，参见 [固定提交 LICENSE](https://github.com/termux/termux-x11/blob/d55f1b7e575de0a7d2b03c5882d5e3d375d01a4f/LICENSE)。发行修补 APK 时同时提供对应源码、补丁、构建脚本和依赖版本，并保留相关许可；发布 APK 不替代源码发布。

libhybris、WSI 和 Android headers 已通过 [sources.lock.json](sources.lock.json) 锁定完整提交，相关改动已保存为完整补丁。libhybris 的整体打包声明不能替代其中 Android/BSD/Apache 等文件的许可；本仓库已收录其上游许可证文本，正式打包仍需按实际内容整理通知。WSI 保留 MIT/Arm 通知，Android headers 保留各文件原有许可。

修改版 libc 作为固定来源和 SHA-256 的外部运行时依赖获取，已与设备工作文件核对。当前流程没有从其完整对应源码重建该文件；对应源码 revision、emutls 修改、构建路径和再分发范围仍需补齐，不能由文件可下载或功能测试通过推导出许可结论。详见 [构建范围](docs/build.md)及 [THIRD_PARTY.md](THIRD_PARTY.md)。

设备固件中的 Mali 驱动作为用户本机运行依赖，不纳入本项目发行包。历史设备脚本保留来源记录，不因放入 `reference/` 就改变其中可能涉及的第三方许可。

正式发布二进制时，还需随附实际组件的许可证与通知、对应源码、工具链和构建记录。顶层 LICENSE 不授权未知来源文件或厂商二进制；当前公开源码更新不替代这些二进制发行准备。
