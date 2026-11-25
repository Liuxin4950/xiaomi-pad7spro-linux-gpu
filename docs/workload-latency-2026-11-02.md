# 2026-11-02 实际工作负载延迟与 Writer 滚动调查

本轮为诊断和独立候选验证，未切换生产入口、库、APK 或桌面，未改变原有 LibreOffice 配置。r3.5 最终版基线保持不变。用户报告鼠标延迟、卡顿，尤其 Word 滚动体感约 20 FPS；这个数值为用户观察，本轮未完成逐帧文档内容测量。

## 主要发现

### Writer 尚未接入硬件文档绘制

所谓 Word 实际是 LibreOffice Writer，包版本 `4:25.2.3-2+deb13u8`。原进程 PID 15410，桌面入口已经经 `gpu-run auto /usr/bin/libreoffice --writer %U` 启动；环境也继承了 r3.5 ICD/WSI 设置。但运行映射是 `libvclplug_gtk3lo.so`、GTK3 和 Cairo，没有 Vulkan loader、WSI 桥和 Mali Vulkan 驱动。仅加载 `libskialo.so` 不证明启用了 Skia GPU。

因此可以确认该 Writer 未使用本项目的 Mali Vulkan 文档绘制路径。这是实际应用覆盖缺口，尚不能单独证明它造成了全部滚动卡顿。排版、文字布局等工作即便启用 GPU 也仍需 CPU。

LibreOffice 对应版本源码明确说明，Linux 上很多 VCL 后端不使用 Skia，应选择支持 Skia 的后端，例如 `SAL_USE_VCLPLUGIN=gen`：

- https://github.com/LibreOffice/core/blob/libreoffice-25.2.3.2/vcl/skia/README
- https://github.com/LibreOffice/core/blob/libreoffice-25.2.3.2/vcl/skia/SkiaHelper.cxx

### 独立 Vulkan 候选未通过

使用私有 UserInstallation、磁盘文档副本和 `--view`，通过统一 `gpu-run` 启动独立进程，设置 `SAL_USE_VCLPLUGIN=gen SAL_ENABLESKIA=1 SAL_FORCESKIA=1 SAL_SKIA=vulkan`。未打开原文件进行写入，没有修改原 profile。

候选 PID 30225 初期加载了 `libvclplug_genlo.so`、系统 Vulkan loader、r3.5 sysvk/libhybris 和 `/vendor/lib64/hw/vulkan.mali.so`。随后发生 `BadWindow`：major opcode 146、minor opcode 3、resource `0x0`，并 SIGABRT。当前 X 扩展表确认 146 为 Present；minor 3 是 SelectInput。此错误指向空/无效窗口的 Present 事件注册，但尚未完成对具体调用者和窗口生命周期的定位，不能认定应修改哪一层。

未得到稳定窗口、`skia.log` 中的有效 Vulkan 后端确认或滚动结果。因此不能声称硬件适配已成功，更不能把初始库映射当作成功验收。候选已经退出，未推广上述环境变量。

### 显示端光标仍与整帧绘制耦合

定版测试源 `build/copy-wake-20261017/test-source/lorie/src/main/cpp/lorie/renderer.cpp` 的 `Renderer::redrawLocked` 将 root、cursor、ownership fence 和 Surface swap 放在同一绘制周期。`lorieMoveCursor` 更新共享坐标并唤醒 renderer。由此推断，最终画面提交拥塞可以影响光标显示；这不是本轮测得的物理输入延迟。

上游 https://github.com/termux/termux-x11/pull/1085 提供 SurfaceControl 独立光标层方案，截至本轮查询仍 open，未合并。它是后续可评估的现成候选，当前没有本机 Mali 的正确性、延迟或功耗 A/B，不能直接部署或宣称收益。当前 `pointerCapture=false`，没有依据直接套用上游外接鼠标捕获问题的修复。

## 当前部署与资源证据

- 统一入口解析到 `/opt/pad7spro-gpu-fps-20261017/bin/gpu-run`，release.json 为 `r3.5-final-20261017`。
- 已安装 APK SHA-256 为 `88346b5831c33e585d467bbf0f8255b972a05dca1ffb112a03bf683404625411`，X server 和 Android renderer 均映射该 APK。
- 当前 X11 命令行为 `-max-fps 120`，display clock 为 `1,120,15`，RandR 119.94 Hz，Android active render rate 120.00001；实际桌面分辨率 3200×2054。设置为 120 不代表 Writer 内容达到 120 FPS。
- XFWM compositing 为 false。原 Trae、QQ、聊天应用 GPU 进程加载了 r3.5 库和原厂 Mali Vulkan 驱动，不能把它们的硬件状态推广到 Writer。
- 初始系统内存约 12/15 GiB 使用，available 约 2.8 GiB，zram 已用约 6.7–7 GiB；zram 的物理压缩占用约 1.9 GiB，不能把交换空间的逻辑使用量当成同等额外物理 RAM。
- 约 29.1 秒计数区间换入 52.66 MiB、换出 38.33 MiB。图形进程也有 major fault；存在回收/换页活动，但没有卡顿时刻的严格关联，不能认定是唯一根因。
- 原混合负载下约 30 秒、120 次 XNoOp+XSync：P50 0.520 ms、P95 1.611 ms、最大 2.934 ms。这测量的是 X server 处理往返，未覆盖设备输入、应用处理、GPU 和屏幕显示整链路。
- vmstat 短样本 CPU idle 约 78–81%；thermalservice 报告 thermal status 0。不能由此排除单线程或瞬时瓶颈，也没有证据声称持续 GPU 饱和。

## 样本有效性

原始文件在 `build/workload-latency-20261102T064641Z/`，包含 passive.json、运行映射、Android input/display/thermal、线程等待和候选日志。该目录含私人文档副本和系统窗口信息，仅保留本地，不应提交 Git 或公开发布。

用户在请求滚动复现后回复“已滚动”。后续 CPU 采样发生在回复之后，Writer CPU 已空闲，未覆盖实际滚动区间。不能用该样本评价滚动性能。用户随后明确确认手动关闭了 Writer 和 Trae，之后的资源变化不构成候选优化收益。

SurfaceFlinger 正确内容层历史为 127 条，存在 8.38 ms 中位呈现间隔和较长间隙，但包含静止、结束滚动与窗口切换，没有对齐连续滚动起止，且是整个 X11 Surface，不能换算成 Writer 内容 FPS。首次层名未规范化的查询没有有效时间戳，已保留作无效样本，不使用其结果。

## 优化优先级与验收

1. 先定位独立 Writer Vulkan 候选的 Present SelectInput/空窗口失败。在私有配置中验证修复，检查真正的 Skia Vulkan 状态、库映射、中文文字、分页、输入法、选择和缩放；通过后再考虑应用入口变更。当前不建议用户把失败的环境变量加入日常入口。
2. 同一份只读文档、同一窗口尺寸/缩放、相同后台负载，先启动采样再开始滚动，比较 GTK3 基线与通过兼容性验收的硬件候选；分别记录输入事件、应用重绘、X11 提交与显示间隔。当前没有量化改善可报告。
3. 若指针自身仍明显延迟，独立评估上游光标层方案，重点验证形状/热点、拖拽、缩放、输入法、休眠恢复和负载下的尾部延迟。需要 APK 的方案仍须先离线构建与备份，由用户安排切换和 Termux 重启。
4. 内存换页作为并行观察项：同负载对比应用换页和停顿关联。不开全局锁频、不关闭系统服务、不自动释放用户工作进程，不以关闭应用后的空闲样本当优化结果。

目标是改善实际文档滚动与输入尾延迟。当前已确认应用后端覆盖缺口并复现候选兼容性失败，尚未得到可推广的修复；没有续航、功耗或稳定 120 FPS 的新增结论。
