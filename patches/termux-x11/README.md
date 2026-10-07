# Termux:X11 GPU Present 补丁

上游：[termux/termux-x11](https://github.com/termux/termux-x11)。

固定基线：`d55f1b7e575de0a7d2b03c5882d5e3d375d01a4f`。

补丁：[termux-x11-gpu-popup-fix.patch](termux-x11-gpu-popup-fix.patch)，SHA-256：

```text
6af0f2604eb610d729fc70b8f90bf2fd63d5e22fa5aeb8af73fc13e7ad572f0e
```

## 修改内容

1. GPU Present 直接写 screen pixmap 时，将更新区域与窗口可见 clip 相交，避免覆盖上层候选框和菜单。
2. 对 redirected compositor pixmap 保留完整内容；临时 Region 在成功、回退及提前返回路径释放。
3. 添加 `-max-fps N`，范围 1–240，限制 X11 RandR 报告值。原补丁中的 `vblank_interval` 仅被赋值，没有参与调度；真正的显示节拍限制由下面的第二阶段补丁补齐。项目参考配置使用 60。
4. 将逐矩形 GPU copy 日志限制为调试模式，减少正常运行时的日志开销。

## 第二阶段：显示节拍与 GPU copy 合并

[0002-pacing-and-copy-batching.patch](0002-pacing-and-copy-batching.patch) 必须在原补丁之后应用，SHA-256：

```text
c518cdc8fd7e53be1a6449cc2541e999e4ca78609dbd6beca55279ba9be0f69a
```

- 显式设置 `-max-fps` 时，在 X server 工作队列中按单调时间戳筛选显示 tick；被跳过的 tick 不递增 MSC，也不重新开放 renderer 绘制。输入和 GPU copy 完成通知使用各自的工作项，继续正常处理。
- 优先使用运行时查找到的 64 位 Choreographer 接口；API 24–28 回退到 `CLOCK_MONOTONIC`，避免 32 位 `long` 时间戳溢出。只保留一个待处理 tick 及最新时间戳，恢复后不回放旧 tick。
- 有显式上限时，flip 完成排到后续有效 MSC；flip 请求不能自行推进显示时钟。未设置 `-max-fps` 时保留原有不限制行为。
- 正常 redraw 将 pending GPU copy 与 root 绘制合用一次 fence；root buffer 缺失或尺寸不匹配、即将提前返回时仍单独完成 copy。保留 swap 后的小绘制兼容处理、可见区域裁剪和 buffer idle/完成规则。
- 每 5 秒额外汇总已处理 tick、被节流 tick 和配置上限，不打印逐帧日志。这些是工作队列处理计数；合并掉的回调不计入其中。

该补丁限制显示时钟与实际 redraw 的开放频率，不进行内容比较，不把无更新区域的 Present 当作静止画面，也不保证异步提交的所有 GPU copy 都降到同一频率。空闲自适应、增量更新区域传输、copy 失败状态与 fence 超时恢复是后续独立工作。

## 获取与应用

以下命令在 **Linux 构建环境** 中运行。先将本补丁保存到构建目录，保持其哈希不变：

```sh
git clone https://github.com/termux/termux-x11.git
cd termux-x11
git checkout --detach d55f1b7e575de0a7d2b03c5882d5e3d375d01a4f
git submodule update --init --recursive
git apply --check /absolute/path/termux-x11-gpu-popup-fix.patch
git apply /absolute/path/termux-x11-gpu-popup-fix.patch
git apply --check /absolute/path/0002-pacing-and-copy-batching.patch
git apply /absolute/path/0002-pacing-and-copy-batching.patch
git diff --check
```

子模块 revision 由固定提交的 gitlink 决定；不要更新到最新 HEAD。补丁修改顶层 `xserver.patch`，子模块本身还需由上游构建过程应用该补丁。

## 构建与签名

固定提交的 Gradle wrapper 使用 `gradle-9.8.0-all.zip`，模块包含 `lorie-app`。按该提交的构建配置准备兼容 JDK、Android SDK/NDK 后执行：

```sh
./gradlew :lorie-app:assembleDebug
```

以上是待在干净环境复核的 APK 构建入口；完整 JDK/SDK/NDK 版本和环境仍需补齐后才能标为已复现。

设备原构建记录写明 universal debug APK 的四种 ABI 编译成功，安装版本为 `1.03.01-d55f1b7-29.09.26`。原 APK 的 SHA-256 为 `cafaa567a76ebd08baa0115629b522ff58697b71738ef5a732b4a0b4da259bcf`，2026-10-07 重新核对一致；其 v2 签名验证通过。仓库不收录 APK。

自行构建的 APK 通常具有不同签名，不能假设它可以覆盖所有来源的现有安装。发布时给出签名证书指纹、升级/回退说明和设置备份方法；不发布签名私钥。

## 本轮验证

2026-10-01 从设备原补丁精确导出，哈希与设备及既有记录一致。取得固定基线的三个原始文件后，执行 `git apply --check --whitespace=error-all`，返回 0。该结果证明对这一基线可以应用，不等于已完成新 APK 构建和实机回归。

2026-10-07 第二阶段补丁在独立源码副本中完成验证：

- 从 `d55f1b7` 原始文件依次检查并应用两个补丁，`--whitespace=error-all` 通过；最终六个文件与验证源码逐字节一致。
- 主机时序回归覆盖 120/90/240 Hz 到 60 FPS、输入频率低于上限、119.94 Hz 加抖动、暂停恢复、重复/回退时间戳以及变更上限；启用未定义行为检查后通过。
- 使用本地 NDK `28.2.13676358` 的 clang 与既有生成配置，为 `arm64-v8a`、`armeabi-v7a`、`x86`、`x86_64` 各编译三个改动单元，共 12 个全部通过；复用这一基线的其他已有对象，四种 ABI 的 `libXlorie.so` 重新链接通过。
- 未全量构建、安装或重启 APK。当前桌面仍使用原 APK；不能把编译与链接通过表述为实机验收。

应用两个补丁后，可在 Linux 主机运行时序回归：

```sh
cc -std=c11 -Wall -Wextra -Werror -fsanitize=undefined \
  -I /absolute/path/termux-x11/lorie/src/main/cpp/lorie \
  /absolute/path/test-frame-pacing.c -o /tmp/test-frame-pacing
/tmp/test-frame-pacing
```

APK 试运行还需验证：Android 120 Hz 配置下 `-max-fps 60` 的 MSC/实际 swap 频率、全屏 flip 与普通窗口 copy、输入法/菜单、连续滚动与视频、窗口缩放、休眠恢复及输入延迟。原固定补丁和原 APK 哈希保持不变，可继续作为回退基线。

## 原生增量候选 APK

2026-10-07 在本地 `out/termux-x11-pacing-20261007/` 准备了 `termux-x11-pacing-native-incremental-debug-20261007.apk`，SHA-256 为 `eba934ca155ae0f77710e4f298539b181b72e9ebb54aa0994e5d7ca4df731fb3`。

离线 Gradle 尝试因缓存版本 `9.3.1` 低于插件要求的 `9.5.0` 而停止。候选包采用**原生增量重打包**：在已核验的原 APK 中只替换四种 ABI 的新 `libXlorie.so`，其他归档内容逐字节保持一致，再执行 `zipalign -P 16` 和 v2 签名。它不是干净全量构建；Manifest、DEX、资源及原版本号均被保留。

签名采用上游 `lorie-app/build.gradle` 的公开测试签名配置。候选和原 APK 的证书 SHA-256 均为 `b6da01480eefd5fbf2cd3771b8d1021ec791304bdd6c4bf41d3faabad48ee5e1`；签名、CRC、16 KiB ZIP 对齐和库内容核对通过，满足覆盖原包的签名条件。候选尚未安装或运行，实机升级和功能验收仍未完成。旁边的 `verification.json` 保存完整验证结果；密钥不随候选产物发布。
