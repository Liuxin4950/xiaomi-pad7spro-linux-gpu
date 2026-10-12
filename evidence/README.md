# 验证记录

更新日期：2026-10-07。这里记录源码开发更新的证据，不表示正式 `v0.1.0` 二进制发行已经验收。

- `reference-manifest.json`：参考脚本与补丁的来源和 SHA-256；包含 2026-10-01 快照及 2026-10-07 已部署的入口更新。
- `debian-package-versions.txt`：2026-10-01 只读取得的部分软件版本，是环境记录而不是可自动安装的锁文件。
- `development-2026-10-07.json`：独立 Linux 开发栈、Vulkan/AHB、swapchain 替换、OpenGL/Zink、Chromium 画面与 WebGL 结果，以及短时 CPU 样本和未测功耗的边界。
- `desktop-migration-2026-10-07.json`：应用、URL/helper、兼容入口及 Termux 会话脚本的迁移文件与前后哈希。
- `software-adaptation-2026-10-07.json`：Chromium、ChatGPT、Trae、CC Switch 的适配与短时结果、默认入口保留情况。
- `benchmark-template.csv`：功耗/稳定性测试的空模板，尚无新测量值。
- `SHA256SUMS`：公开源码、文档与参考文件的哈希清单，不含本清单自身；每次公开更新后需重新生成。

2026-10-01 的准备记录主要是文件核对、补丁应用和语法检查。2026-10-07 已完成独立构建安装及真实应用窗口验证；用户随后重启当前会话并反馈可用。部分 JSON 保存的是当日较早阶段的状态，例如尚未重启会话或尚未完成 WebKit 适配；解读时结合 [当前状态](../docs/development-status.md)，不要把阶段性快照当作永久结论，也不要把用户反馈扩展成未记录的长时测试。

原始本机运行日志、Android 截图和短时采样位于 `build/runtime-20261007*`，不随源码仓库发布。显示端候选 APK 的原生编译、增量重打包和校验范围见 [Termux:X11 补丁说明](../patches/termux-x11/README.md)。早期候选日期为 2026-10-07；2026-10-12 已部署含其原生批处理的 gpu-direct 包，老 X server 仍需正常重开。当前状态见 ../docs/CURRENT-STATE.md。

仍未完成干净 rootfs 安装复现、修改版 bionic 完整源码重建、同条件长时功耗/续航对照及视频硬解验证。短时不同实际帧率的 CPU 样本不能用于计算功耗节省比例。当前文档更新没有额外运行构建、测试或功耗采样。

新测试应新增独立记录，给出源码/组件版本、测试条件、原始样本、退出状态和结论。保留旧记录的时间与适用范围；没有测量的项留空或写“未测”。

## 2026-10-12 r3 候选效率审查

[r3-efficiency-2026-10-12.json](r3-efficiency-2026-10-12.json)保存系统异常循环、探索性 host 帧间隔/CPU 对照、定向验证和持续测试结果。这是早期 r3 审查，当前默认已为 r3.3；这些数据不代表整机功耗、屏幕 scanout 或真实输入延迟。[完整审查](../docs/r3-efficiency-audit.md)。

最新：`r3.3-native-rendering-2026-10-12.json` 记录二维原生 Vulkan 和输入接口核对；`entrypoints-2026-10-12.json` 记录全部入口迁移。旧 evidence 数值不修改。
