# Termux:X11 GPU Present 补丁

2026-10-17：补丁至 0014 已随最终 r3.5 定版；不因旧章节中的“候选/下一步”继续自动换包。当前验收和归档见 [r3.5 最终说明](../../docs/r3.5-efficiency.md)。

更新：2026-10-17。当前 APK SHA-256 `88346b5831c33e585d467bbf0f8255b972a05dca1ffb112a03bf683404625411` 已干净构建、安装，X server / Android renderer 两端映射核对通过。补丁完整顺序以 `sources.lock.json` 的 `termux_x11.patches` 为准；0009–0011 与 WSI 0012 为前一轮联合验收基线；新增 0012/0013 的实际结果和边界见文末。下文早期阶段的构建命令、60 FPS、候选未安装和 swap 后预热说明均为历史，请使用 [当前构建流程](../../docs/build.md)与 [CURRENT-STATE](../../docs/CURRENT-STATE.md)。

0014 已经用户授权安装并由用户重启；两端实际映射均为 `88346b58…`。standalone 比例由旧诊断 17.47% 降到 0.47%，712704 个物理像素零差异；默认页面仍约 112–116 rAF/s，持续实际 120 帧目标未完成。

上游：[termux/termux-x11](https://github.com/termux/termux-x11)。

固定基线：`d55f1b7e575de0a7d2b03c5882d5e3d375d01a4f`。

补丁：[termux-x11-gpu-popup-fix.patch](termux-x11-gpu-popup-fix.patch)，SHA-256：

```text
6af0f2604eb610d729fc70b8f90bf2fd63d5e22fa5aeb8af73fc13e7ad572f0e
```

## 修改内容

1. GPU Present 直接写 screen pixmap 时，将更新区域与窗口可见 clip 相交，避免覆盖上层候选框和菜单。
2. 对 redirected compositor pixmap 保留完整内容；临时 Region 在成功、回退及提前返回路径释放。
3. 添加 `-max-fps N`，范围 1–240，限制 X11 RandR 报告值。原补丁中的 `vblank_interval` 仅被赋值，没有参与调度；真正的显示节拍限制由下面的第二阶段补丁补齐。历史参考配置使用 60；2026-10-16 起当前默认已改为 120。
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

## 输入法接口补丁与当前构建

`0003-ime-cursor-cancellation.patch` 返回不支持实际光标几何更新，取消请求不回调；文本/组合/selection/按键路径不变，避免虚构 CursorAnchorInfo 触发搜狗忙循环。依次应用 0001、0002、0003，哈希以 sources.lock.json 为准。

实机构建使用本地 Gradle 9.3.1、AGP 9.1.0、compileSdk 36 / targetSdk 34、buildTools 37 ARM aapt2/aidl、JDK 21，关闭新 DSL 和 companion 生成；保留已校验 0002 的四种 ABI 原生库作为 jniLibs，不执行 externalNativeBuild，构建 `:lorie-app:assembleStandaloneDebug`，同上游测试证书。这个 Java/资源构建 + 既有原生库的方法不是干净全量 NDK 复现。APK 和全量日志在忽略目录 build/native-display-20261012。

## r3.4.2：按需显示时钟候选

新增 [0004-demand-driven-display.patch](0004-demand-driven-display.patch)，顺序为 popup → 0002 → 0003 → 0004。发布协作时钟属性、BlockHandler 按现有 Damage/光标/Present 工作请求 Choreographer、虚拟 MSC 跨空闲连续、关闭默认统计 timer，新增 opt-in atrace/EGL 呈现诊断。与 WSI 0008 协作；旧桥接继续使用原来的限帧，新桥接对旧 APK 使用 timer 回退。

顶层与嵌套 Xserver 补丁对锁定提交均通过；四 ABI 增量编译/链接、16 KiB APK 对齐和原签名核对完成。候选未安装，不能认为空闲唤醒或显示 P99 已改善。原 APK 保存、DEX/资源保持一致，重开桌面需先保存全部 chroot 会话。范围与验证条件见 [显示效率记录](../../docs/r3.4-display-efficiency.md)。

0007-copy-failure-feedback.patch 在 0006 后应用，区分安全完成与成功复制，失败清除消费端历史并报告 SKIP；共享头变更必须同步重编四 ABI 的全部引用单元。最新构建/安装范围以 CURRENT-STATE 与 r3.5 收尾证据为准。

## 碎片化 damage 的 GPU 拷贝回退修复候选

[0008-present-fragmented-damage-gpu-copy.patch](0008-present-fragmented-damage-gpu-copy.patch) 在 0007 后应用，SHA-256 `016ce9e4c2cd63ddf7d99a7bb2c8da08d7cc4a5953a917b5c1afdbc35ae81399`。修改嵌套 `patches/xserver.patch` 中的 Present 实现，以及顶层 `lorie/InitOutput.c`；不能直接提前修改尚未应用嵌套补丁的 xserver 子模块。2026-10-17 首次干净构建发现原封装顺序不兼容，已修正封装；运行逻辑与交接版本逐字节核对一致（头文件仅修正边界注释）。

原实现拒绝超过 `LORIE_GPU_COPY_MAX_RECTS`（16）块的 GPU 拷贝。候选在裁剪后区域超过 `LORIE_GPU_COPY_WIDEN_RECTS`（8）块时，改用“完整可见源”超集拷贝；写入真实 screen pixmap 时仍与 clipList 求交，保留弹窗/IME 遮挡。若完整可见区本身仍超过 16 块，仍会安全回退 CPU；阈值 8 不保证最终矩形数低于 16。区域放大不收窄 damage 提示，不改动消费端历史与失败修复语义。

新增 `PAD_X11.CopyFallback.<reason>.<rects>` 埋点：1=禁用/legacy，2=无渲染器，3=缓冲不可采样，4=矩形数为零或超限，5=队列满。已有采样证明卡顿期间大量时间用于 tick 线程的 pixman 拷贝；**具体拒绝原因仍待新版埋点确认**，不能把“超过 16 块”写成已证实根因，也不能据此直接扩展缓冲或队列实现。构建、部署及验收状态见 [CURRENT-STATE](../../docs/CURRENT-STATE.md)。


## 精确裁剪区域的原子 GPU 分批候选

[0009-atomic-clipped-copy-chunks.patch](0009-atomic-clipped-copy-chunks.patch) 在 0008 后应用，SHA-256 `7f30833935093a42ef202e93191a1e0546228d9640a39f39852b10486a2e981d`。0008 的实际验收抓到最终区域仍为 25 块，超过单项 16 块限制；其全可见源放宽未消除 CPU 回退。

0009 撤掉放宽，保留精确 damage/clipList，把一个 Present 分成多项（每项最多 16 块）后一次发布，沿用现有 8 项共享队列。所有分块共用一个 Present serial、一次源/目标引用和同一完成栅栏；首块失败也会使该 Present 报告失败，不能提前 Idle。容量不足时不发布部分工作、不取得引用。队列 ABI 和字段布局不变；最多 128 块，超量/容量不足保留安全 CPU 回退。

干净 arm64 构建与签名、16 KiB ZIP 对齐、原生库哈希通过。以下定向回归直接提取已打补丁的生产 C 函数与共享队列类型，用主机缓冲 stub + UBSan 检查精确裁剪、边界/回绕、原子容量、分组失败和 root/redirected 引用；旧实现负向对照在 17 块失败。这不是物理屏幕验收。

```sh
python3 tests/run-x11-copy-regression.py build/x11-rect-chunks-20261017/source
```

候选已直接覆盖安装并打开 Activity，未运行 zink 脚本；服务端尚待保存工作后的重启及实机验收。状态与哈希见 [分批候选证据](../../evidence/present-copy-chunks-2026-10-17.json)。


## 根缓冲的按需 CPU 映射候选

[0010-scoped-root-cpu-access.patch](0010-scoped-root-cpu-access.patch) 在 0009 后应用，SHA-256 `8984d9f88984866c00ea1c5ddbbd91038afe38731e03633b4b18e90ff75c35ec`。0009 的真实采样已消除矩形数回退，帧率约 82/s；剩余 X server CPU 成本主要在 `lorieRedraw` 对整屏 AHB 做不必要的 CPU lock/unlock 缓存维护。

0010 发布根缓冲时结束已有 CPU 映射，纯 GPU 帧不立即重新映射；切到 GPU 生产的 AHB root 也不开始 CPU 访问。真实 CPU 绘制仍由 EXA PrepareAccess/FinishAccess 映射，缓存刷新发生在释放 GPU 所有权锁之前；映射失败时不遗留该锁。legacy FD 映射周期、共享 ABI、队列、GPU fence 和厂商 Mali 不变。

扩展 `tests/run-x11-copy-regression.py PATCHED_SOURCE` 检查按需 root 映射、真实 CPU 写入/读回、先刷新后释放 GPU 锁、失败解锁与持久 regular/FD 映射；故意恢复错误释放顺序的负向对照会失败。主机回归和干净 arm64 构建、签名/对齐/包内库校验通过，候选已直接安装；服务端尚待切换，不能宣称已取得帧率或功耗收益。完整范围见 [证据](../../evidence/scoped-root-cpu-access-2026-10-17.json)。


## CPU access 与已排队 GPU 拷贝的顺序

[0011-order-cpu-after-queued-gpu-copy.patch](0011-order-cpu-after-queued-gpu-copy.patch) 在 0010 后应用，SHA-256 `a4fd4c215bcab83f5e4a477c6407f3360956ae7aaca96ead84044cf98b456dc7`。配合 WSI 两在途调度时，曾实测一块后来绘制的弹窗被旧 clip 的已排队 GPU 拷贝覆盖（800 像素），不能只靠 renderer mutex 排除尚未执行的工作。

CPU access 现在等待此前发布的 GPU serial ownership watermark，等待时让出 renderer mutex；不能等待由同一 X server 主线程处理的 Ack 计数。GPU 完成独立发布水位，断连/2 秒超时则拒绝不安全访问。生产函数 UBSan 回归覆盖排队先后、等待期间让锁、没有 Ack 的进展以及失败拒绝；绕过水位的负向对照会失败。共享队列 ABI 不变。

最新 APK `c62abdc5…` 与 WSI 0012 的联合实机验收已通过：25 矩形遮挡两幅图各 307200 像素零差异，另有增量/空列表、重建/Flip 和真实 Chromium 验证。结果及当前生效范围见 [FPS 交付证据](../../evidence/fps120-release-2026-10-17.json)，前文候选未验收描述为历史阶段。


## 2026-10-17：刷新许可与最终 Surface 提交

0012 在开始渲染前原子领取现有 byte 许可；tick 在 GPU 等待期间到达时仍可供下一帧使用，完成时不再次覆盖许可。共享布局与所有权栅栏保持原协议。0013 将离屏拷贝放在最终 Surface 清屏之前，根画面和光标之后创建共同栅栏并只显式 flush 一次。

`tests/run-x11-copy-regression.py` 直接提取实际 `Renderer::redrawLocked` 执行 GL/所有权 stub 回归，覆盖 tick 与等待交错、忙许可、无效根缓冲排空，以及 copy→clear→root/cursor→fence→flush→wait→unlock 顺序；旧绘制顺序和晚覆盖许可的负向对照均失败。干净 arm64 构建、同 v2 证书、CRC/16 KiB 对齐及两端实际映射通过。当前短样本 SF 内容层约 117.18/s，712704 物理像素零差异；持续独立页面 120 帧目标尚未完成，不能据此声称长期流畅或省电。

两次 APK 替换均伴随当前会话中断；后续先完成候选和备份，再通知用户安排 Termux 重启。原始测量、候选版本及回退见 [本轮证据](../../evidence/display-permit-surface-submit-2026-10-17.json)。

## 2026-10-17：tick 内的 GPU 拷贝通知

[0014-defer-tick-copy-wake.patch](0014-defer-tick-copy-wake.patch) 在 0013 后应用。tick 的 vblank 循环曾在许可仍关闭时发布并通知 GPU copy，renderer 可能先走 standalone 拷贝与栅栏，再为 root 绘制另做一次提交。匹配独立浏览器 pixmap 的诊断记录中，647 个 copy serial 有 113 个 standalone；这包含合法的独立排空，不等于全部都是可消除的开销。

0014 只在服务器线程局部延后普通 enqueue 通知：照常 release 发布队列，vblank 循环结束后先开放已有 byte 许可，再为尚未排空的队列通知一次。循环外的 enqueue、CPU 等待既有 GPU watermark 的唤醒、已运行的 renderer 排空均保留，避免 CPU fallback 等待停住；共享 ABI、引用、队列容量与所有权栅栏不变。

实际生产 C enqueue/CPU/tick 函数和 C++ redraw 的 UBSan 回归通过，三个故意错误版本被拒绝；主机测试输入与正式构建源码逐字节一致。干净 arm64 构建的 APK SHA-256 为 `88346b5831c33e585d467bbf0f8255b972a05dca1ffb112a03bf683404625411`，同 v2 证书、CRC、包内库哈希和 16 KiB 对齐通过。构建时尚未安装；现已由用户协调切换，真实正确性和通知合并检查通过，但没有稳定 120 或新功耗结论。旧包备份与完整验收见[候选证据](../../evidence/deferred-copy-wake-2026-10-17.json)。
