# 当前验证状态

更新：2026-10-17。当前新默认为 **r3.5-fps-20261017 / copy-chunks-scoped-root-cpu-bounded-wsi-pipeline**，唯一配置基线见 [CURRENT-STATE](CURRENT-STATE.md)，集成范围见 [r3.5](r3.5-efficiency.md)。

FPS 修复的 APK 与新默认栈已联合验收，3000 帧约 116.84 次提交/秒、Chromium 约 119.45 rAF/s，物理像素检查通过；一个已打开应用仍需正常重开加载新 WSI。见 [最新证据](../evidence/fps120-release-2026-10-17.json)。2026-10-13 的 [全域替换证据](../evidence/r3.5-global-switch-2026-10-13.json)保留为历史。受控像素/Chromium 核心验收已取得，真实输入延迟、长期能耗、全部应用与恢复场景仍不作完成承诺。

后续按 [优化计划](gpu-optimization-plan.md) 执行。2026-10-15 已完成首批独立构建、版本明确的测量与可恢复部署，并通过新 APK/前缀的核心像素与设备验收；不能把工具修复计为 GPU 帧率或省电收益。

## 历史：2026-10-13 r3.4.1 与候选阶段

以下运行版本与未安装描述均为当时快照，不能代替当前 r3.5 实装状态。

已实施：Mali 真正硬件渲染；Skia 原生 Vulkan 二维后端；WebGL ANGLE Vulkan；WSI 指令复用、FIFO 空闲休眠、Complete-before-Idle 释放修复、可配置呈现上限（2026-10-16 新会话默认 120 fps，已有会话仍为 60）；Termux 前端 Copy/绘制合并；拒绝不存在的真实 Linux 光标几何请求；全部正常桌面/菜单/Widget/CLI 入口统一；r3.4.1 修正增量呈现语义与所有轮换 AHB 的 damage 历史，保留局部拷贝并移除空列表跳帧，新增重叠矩形合并与默认关闭的有界实时计数（[r3.4 交付](r3.4-damage-aware-copy.md)）。

已取得运行证据：Chromium/Trae GaneshVulkan + Mali + 0 GPU 崩溃，WebGL 颜色回读正确；同一滚动页 rAF 35.83→58.86/s，CPU/页面帧 10.43→8.39 ms。r3.4 的旧测试沿用错误语义，计数保留为历史，不能证明画面正确。r3.4.1 核心探针通过，独立逐像素回归（原版失败、修版通过）覆盖 BGRA copy/blit 与两种命令复用；随后恢复桌面并完成真实窗口、最终帧屏幕像素和 Chromium/Trae GaneshVulkan + Mali + 0 GPU 崩溃验收。小动画 WSI 复制像素少 72.03%；受控局部 UI 的稳定 128 帧窗口，Chromium/Trae 少 99.42% / 95.26%，均为复制工作量而非功耗。数据/范围见 [r3.4 审查](r3.4-damage-aware-copy.md)、[r3.3 交付](r3.3-native-rendering.md)。

当前系统链接指向 `/opt/pad7spro-gpu-r3.4.1-opt1`，初版修复与 r3.3 完整保留。没有停止已有应用；文件升级不代表进程热更新。

尚未证明：局部/静止路径的整机功耗收益、用户真实编辑/输入/浏览场景的视觉验收、所有应用与工作流兼容、长期续航、休眠恢复、视频硬解、完整中文触控输入、物理屏幕所有尾延迟消除、零拷贝。页面 rAF 不是实际新内容屏幕 FPS，单位帧 CPU 减少不等于整机功率相同比例减少。

系统异常记录：daemon 的 NULL subclass 导致循环上传已用同 PID 单记录干预确认并规避；记录与一致备份保留，固件修复仍需小米。搜狗满核进入 CursorAnchorInfo/Xposed Hook，拒绝不可用接口后的末八个一秒样本均为 0 CPU 时间；HyperCeiler 作用范围未变。

历史 2026-10-07 / 早期 r3 测试保留在 evidence 和阶段文档，不能用旧的"默认 r2 / 候选 APK 未安装"描述当前设备。正式公开发行仍受 RELEASE-CHECKLIST 约束，当前是已部署的源码开发版本。

本轮证据见 [r3.4.1 优化](../evidence/r3.4.1-optimization-2026-10-13.json)。下一步优先实际日常页面/输入与受控放电数据；不要按空 damage 跳帧，不凭链路层数删除同步或改系统服务。

### 2026-10-13：显示效率技术候选

r3.4.2 完成 WSI/Termux:X11 协同节拍、按需 Choreographer、空闲统计 timer 关闭与有界帧关联诊断。独立桥接和四 ABI 增量 APK 已构建，正确性/入口与旧 APK 兼容窗口通过。新 APK 未安装、桌面未重启，端到端 P95/P99、输入响应、APK 空闲对照、长期温升/功耗验收待进行；默认仍为 r3.4.1。详见 [技术迭代](r3.4-display-efficiency.md)。视频/MediaCodec 和 WebKit 属于未实施专项，不计为本轮已完成特性。

部署后运行状态已更新至 [整链路结果](r3.4-display-results.md)。本页“未安装/未重启”表述属于候选构建完成时的历史快照；实际是否保留新 APK 或自动回退，以结果中的实装哈希为准。默认桥接未自动推广。
