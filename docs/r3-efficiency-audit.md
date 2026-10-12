# r3 效率审查与设备验证（2026-10-12）

本轮在平板的 Debian root chroot 内实施。日常入口仍指向 r2；r3 是独立候选，未重启 X11、安装 APK、修改 Android 调度组或系统服务。没有足够证据宣布日常卡顿和整机功耗已经改善。

## 真实链路和已排除项

应用 → ANGLE 或 Zink → Vulkan loader → sysvk/libhybris → 原厂 Mali；sysvk 是薄转发，层数本身不能作为性能结论。真实进程映射和 Chromium 读回确认使用 Mali-G925-Immortalis（Vulkan 1.3.278），没有软件回退。

```mermaid
flowchart LR
 A[真实 BGRA VkImage] -->|WSI GPU Copy| B[私有 RGBA AHB 内保存 BGRA 字节]
 B -->|DRI3 / Present| C[Termux:X11 GPU Copy 或 flip]
 C --> D[Android renderer / SurfaceFlinger]
```

- 当前不是 proot；无须通过替换 proot 消除开销。
- XFWM 合成已关闭；应用 WSI 已有 60 FPS 的阻塞式上限。
- `QueueWaitIdle` 在 WSI 退役/析构中，不是每帧调用；不能直接移除。
- BGRA 中间图像、AHB、command pool 已按图像复用，并非每帧重新分配。
- WebKitGTK 仍使用 GPU 合成 + SHM，包含独立读回成本，本轮未改动该链路。

## 已确认的消耗和不确定的主因

### 系统异常循环：与桥接分开处理

10.004 秒 Perfetto 基线中 `com.miui.daemon` 使用 10.668 CPU 秒，其中 `CoreEventUpload` 8.682 秒、`HeapTaskDaemon` 1.815 秒；另有 analytics 2.766 秒、logd 2.601 秒。日志快照 1.140 秒内观察到 133 次 `ExceptionUploader` 空指针异常，约 115.8 次/秒，来源为 `String.contains` 的 null 对象。

这是实测的系统后台消耗和调度干扰，尚不能单凭它认定所有掉帧的根因。没有关闭、停用或修改这些服务。基线同时存在用户活动、输入法和其他应用，不属于静止桌面功耗测量。

原始 Perfetto 配置保存为 [reference/perfetto-gpu.cfg](../reference/perfetto-gpu.cfg)，使用系统 `perfetto --txt -c CONFIG -o TRACE` 录制。分析器为 Perfetto 官方 v58.2 arm64 预构建，按官方 manifest 校验哈希；trace 无非零 error severity 的数据丢失统计。

### 调度与显示等待

- 应用/GPU 进程：cpuset `/debian`，CPU `/top-app`，允许 CPU 0–9。
- Termux:X11 服务关键线程：cpuset/CPU `/foreground`，实际 affinity 5–7；其他线程可能为 2–7。参考启动脚本没有对应的 `taskset`，限制来源尚未定位。
- Perfetto 中 X11 服务主线程累计 runnable 179.6 ms/10 秒，Android X11 主线程 276.0 ms；最长单段 runnable 等待约 4.3/8.0 ms。它们是调度等待，不是端到端输入延迟。
- 实际 FrameTimeline 数据只有 SurfaceFlinger、SystemUI 和其他少量图层，未捕获可直接归属 Termux:X11 的 surface 帧，不能从该 trace 宣称其 scanout P95/P99。

[上游 #1022](https://github.com/termux/termux-x11/issues/1022)描述的是三星应用受限的场景；本机应用已经能使用 CPU 0–9，不能直接照搬 sharedUid 或整合 APK。

### 图像搬运与同步

每个 BGRA Present 包含整张图像的 GPU Copy。3200×2054、4 字节、60 帧的单次整图读+写理论字节量为约 3.15 GB/s；这不是实测 DRAM 带宽，也不包括缓存/压缩影响，不能据此计算功耗。

实际格式查询：普通 optimal BGRA 可用；当前测试的 linear AHB + color attachment/transfer dst/sampled usage 下，RGBA 返回成功、BGRA 返回 `VK_ERROR_FORMAT_NOT_SUPPORTED`。这只排除了该配置的直接 BGRA 导出，未穷尽全部 tiling、usage 或导入方案。

事件线程在有 pending completion 时仍保留 100 ms 的 XCB special-event 队列重查，因为其他 XCB reader 可能先取走 socket 数据；空闲无 pending 时是条件等待。是否造成实际尾延迟仍待关联跟踪，不能盲目改成无限 FD 等待。

不能简单把 Copy 换成 Blit：现用 Xorg 协议消费 BGRA 字节，普通色彩转换会重复交换红蓝。没有实现或宣传端到端零拷贝。

## 局部修改

代码在独立分支 `codex/r3-wsi-efficiency`，安装于 `/opt/pad7spro-gpu-dev-20261012-r3`。

1. **FIFO 空闲等待**：`swapchain_base::page_flip_thread` 改为无超时阻塞；`teardown` 清除原子运行标志并 post，worker 在取 pending 队列前检查退出。避免空队列 pop 和 250 ms 周期唤醒。
2. **条件变量正确性**：`timed_semaphore::wait` 按 token 谓词循环，虚假通知不消耗 token；有限超时只计算一次截止时间。
3. **重复指令复用**：`record_conversion` 首次记录 UNDEFINED 初始化，第二次记录 GENERAL/FOREIGN 稳定路径，此后复用。保留上一帧 fence、producer semaphore、完整 Copy、X11 Idle/acquire 和销毁等待。移除可复用 command 的 ONE_TIME_SUBMIT 标记；没有增加图像或跳过帧。
4. **默认关闭的 WSI 诊断**：`PAD_GPU_WSI_TRACE=1` 记录 host payload 准备、producer-ready 等待、X11 请求间隔，退出时汇总；每项只保留最近 1024 个样本，无逐帧日志/分配。`gpu_ready_wait` 包含应用渲染、Copy、驱动与调度等待，不是纯 Copy GPU 时间；X11 请求间隔不是屏幕帧时间。
5. **复现工具**：探针增加尺寸、延时、空闲等待、CSV 和安全退出；`benchmark-wsi.py` 使用相同 client 和帧策略轮换 r2/r3，核查 Mali 与前缀映射。补丁获取器使用临时 Git index 按顺序验证依赖补丁，缓存保持干净。

[命令缓存的生命周期依据](https://docs.vulkan.org/spec/latest/chapters/cmdbuffers.html)：不带 ONE_TIME_SUBMIT 的 command 在完成后回到 executable，复用仍必须等待前次执行完成。

## 对照数据与结论

首轮每变体 3 次、每次 300 帧，固定 60 FPS、同一 X11、同一 client；前 20 帧不纳入 host 帧间隔百分位。表格是三次百分位/总 CPU 的中位数，不是聚合所有样本的百分位。

| 场景 | 变体 | host P50/P95/P99（ms） | client 总 CPU（秒/300 帧） |
|---|---|---|---|
| 640×480 FIFO | r2 | 19.360 / 44.942 / 56.488 | 0.766 |
| 640×480 FIFO | r3 重录 | 16.890 / 38.362 / 51.504 | 0.757 |
| 640×480 FIFO | r3 复用 | 16.704 / 26.760 / 43.714 | 0.784 |
| 3200×2054 FIFO | r2 | 16.731 / 23.296 / 29.754 | 0.864 |
| 3200×2054 FIFO | r3 重录 | 16.782 / 22.659 / 29.927 | 0.877 |
| 3200×2054 FIFO | r3 复用 | 16.689 / 22.551 / 28.754 | 0.882 |
| 640×480 MAILBOX | r2 | 16.790 / 17.504 / 19.263 | 0.480 |
| 640×480 MAILBOX | r3 重录 | 16.788 / 17.485 / 18.722 | 0.514 |
| 640×480 MAILBOX | r3 复用 | 16.788 / 17.834 / 19.494 | 0.540 |

首轮 r3 开启 WSI 诊断，r2 不具备该诊断；client 总 CPU 包括启动和后台驱动线程。部分轮次与短时构建/兼容性工作重叠，系统异常循环和用户操作未控制，因此以上是探索数据，不是严格功耗或日常流畅度验收。关闭诊断、每轮 600 帧的 MAILBOX 复测中，r2/r3 复用总 CPU 三轮中位数为 1.093/0.826 秒，host P95 为 18.087/18.083 ms、P99 为 19.767/19.887 ms。该复测同时有固定合成负载在后台，首轮还与多窗口短验证重叠，同样不属于严格受控验收。这一组总 CPU 下降约 24%，与前一组趋势不同；尾延迟基本不变，尚不能证明日常整体收益稳定。

同一 r3 binary 开/关复用的定向对照更有解释力：300 次 Copy 的指令录制从 300 次变为 8 次（4 张图像各两次）。host payload P50 的三轮中位数，小 FIFO 111.8→54.4 µs，大 FIFO 139.0→80.6 µs，MAILBOX 105.8→49.2 µs。该局部工作确实减少，但只占 16.7 ms 帧预算的小部分，无法解释所有几十毫秒的尾延迟。

空闲 4 秒的 futex 跟踪中，r2 FIFO worker 约 16 次周期超时，r3 对应 worker 为无期限等待；保留驱动自身超时。没有把所有驱动唤醒都算成 WSI 唤醒。

## 验证与剩余验收

- 独立锁定源码构建、安装、Vulkan 真实提交读回、AHB 发送接收释放读回通过。
- 27 项启动器测试通过；真实 WSI mock 在复用开/关两种模式下通过，覆盖虚假唤醒、空闲取消、producer fence、Idle 先于 Complete、deferred/alias、分配失败和资源计数。
- FIFO、MAILBOX 各 50 次 oldSwapchain 替换通过；两个并行窗口各 50 次替换通过；FIFO/MAILBOX 各 50 次真实窗口尺寸交替（256×192 / 240×176）与 oldSwapchain 替换通过。
- Chromium ANGLE Vulkan/Mali、WebGL1/2、红色读回 `[255,0,0,255]` 与真实窗口通过；另完成独立 profile 的 50 次本地页面导航和逐次 WebGL1/2 读回，GPU PID 未重建。这不代表历史 `AllocateRingBuffer` 问题已在真实网页负载下修复。Zink 实际齿轮窗口约 59 FPS。它们是短时兼容性证据。
- 20 分钟合成连续提交通过：52196 帧，持续 1200.5 秒，退出码 0 且正常释放。10 秒后 RSS 从 47944 KB 到 27720 KB，没有持续增长，线程数保持 4。整个 run 的 host 间隔 P95/P99 为 26.22/28.36 ms（含人为 20 ms 延时），最大 409.7 ms，仍有 4 个超过 100 ms 的间隔，不能称作卡顿已解决；测试在日常会话中运行，可能被其他窗口遮挡或受桌面切换影响，不能把 host Present 等同前台完整显示负载。这属于合成负载，不能代替 Trae 编辑、中文输入、网页导航、触控延迟、睡眠恢复或续航验收。

## 未实施的方向和下一步

- **不重写 ICD/libhybris**：没有证据表明薄转发或 ABI 兼容是主要热点。
- **不删 producer fence/析构 WaitIdle**：没有传入 X11 的可靠 producer native fence，GPU 完成与 consumer Idle 必须分开。
- **不做内容去重或 damage 局部 Copy**：当前没有可靠的应用 damage 与 swapchain 历史内容契约，未更新区域不能推断成所有 buffer 内容相同。
- **不强制零拷贝或 native RGBA**：现用颜色契约和测试能力不满足；需要双方协同、格式/usage 探针及生命周期验证。
- **不永久绑大核、改内核/SELinux、换 APK/sharedUid**：当前缺少受控收益证据。旧 X11 `-max-fps` 仍主要是 RandR 报告值，已准备的第二阶段候选 APK 应在保存工作后独立 A/B；本轮没有安装。
- **不套浏览器激进参数、不统一 WebKit**：现有真实后端可用；JS、布局、输入法和 SHM 成本需独立 profile。

下一阶段优先定位异常上传循环；再在受控静止/滚动工作负载中对候选 X11 节拍与 copy-fence 合并做 A/B，记录真实 surface swap/MSC、WSI 与输入事件关联。如果这部分主导延迟，才继续 native fence 或 buffer 协议改造。

## 使用、回退与产物

默认入口没有切换，日常使用仍是 r2。试用前先完整退出同一应用的既有实例，避免单实例机制把请求转发给仍运行的 r2。临时试用单个应用：

```sh
/opt/pad7spro-gpu-dev-20261012-r3/bin/gpu-run chromium
/opt/pad7spro-gpu-dev-20261012-r3/bin/gpu-run gl application
PAD_GPU_WSI_REUSE_COMMANDS=0 /opt/pad7spro-gpu-dev-20261012-r3/bin/gpu-run chromium
```

应完整退出试用实例后从原图标重新打开 r2，已有应用库不会热替换。保留的默认链接目标为 `/opt/pad7spro-gpu-dev-20261007-r2/bin/gpu-run`。若以后改过默认链接，可恢复：

```sh
ln -sfn /opt/pad7spro-gpu-dev-20261007-r2/bin/gpu-run /usr/local/bin/gpu-run
```

结构化结论：[evidence/r3-efficiency-2026-10-12.json](../evidence/r3-efficiency-2026-10-12.json)。原始 CSV/日志、私有测试 profile、截图、Perfetto trace 保存在忽略的 `build/r3-*` 下，不提交个人页面、应用 profile 或二进制。

复现新对照：

```sh
python3 scripts/benchmark-wsi.py --output build/new-ab --runs 3 --frames 600
python3 scripts/benchmark-wsi.py --output build/new-ab-traced --runs 3 --frames 600 --trace
```

本轮没有 r2/r3 整机功耗或真实输入延迟结论，尚不满足设为默认版本的标准。
