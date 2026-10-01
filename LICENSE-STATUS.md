# 许可证状态

顶层 [LICENSE](LICENSE) 使用 MIT，适用于本项目新编写的 `src/`、构建脚本和原创文档。上游源码、补丁与第三方头文件继续使用各自的许可证，不能将它们整体改为 MIT。

`vendor/aosp/hardware/hwvulkan.h` 保留 AOSP 的 Apache-2.0 版权头及同目录下的许可证文件。本项目重新编写了 sysvk/AHB 包装代码，不包含旧来源不明的实现；旧参考脚本的来源整理仍需在正式发行前完成。

Termux:X11 基线采用 GNU GPL v3，参见 [固定提交 LICENSE](https://github.com/termux/termux-x11/blob/d55f1b7e575de0a7d2b03c5882d5e3d375d01a4f/LICENSE)。发行修补 APK 时同时提供对应源码、补丁、构建脚本和依赖版本，并保留相关许可；发布 APK 不替代源码发布。

libhybris 的整体打包声明不能替代其中 Android/BSD/Apache 等文件的许可。WSI 保留 MIT/Arm 通知。修改版 libc 作为明确来源和哈希的外部运行时依赖获取；完整源码构建与再分发范围仍需区分，详见 [构建范围](docs/build.md)及 [THIRD_PARTY.md](THIRD_PARTY.md)。

发布二进制时还需包含实际组件的许可证与通知、对应源码和构建记录。顶层 LICENSE 不授权未知来源文件或厂商二进制。
