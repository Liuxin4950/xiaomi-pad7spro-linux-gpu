# 当前验证状态

更新：2026-10-12，默认 r3.3。唯一配置基线见 [CURRENT-STATE](CURRENT-STATE.md)。

已实施：Mali 真正硬件渲染；Skia 原生 Vulkan 二维后端；WebGL ANGLE Vulkan；WSI 指令复用、FIFO 空闲休眠、Complete-before-Idle 释放修复、固定节奏 60 fps 上限；Termux 前端 Copy/绘制合并；拒绝不存在的真实 Linux 光标几何请求；全部正常桌面/菜单/Widget/CLI 入口统一。

已取得运行证据：Chromium/Trae GaneshVulkan + Mali + 0 GPU 崩溃，WebGL 颜色回读正确；同一滚动页 rAF 35.83→58.86/s，CPU/页面帧 10.43→8.39 ms。28 项启动器检查通过，既有 WSI 生命周期回归通过。数据/范围见 [r3.3 交付](r3.3-native-rendering.md)。

当前已有进程不是热更新：旧 X server 的真实显示 tick 上限与旧 ChatGPT 的二维后端在正常重开后才生效。新 APK 已安装，前端和新应用已使用更新。目录名 observe 不代表日常开启诊断。

尚未证明：所有应用与工作流兼容、长期续航、休眠恢复、视频硬解、完整中文触控输入、物理屏幕所有尾延迟消除、零拷贝。页面 rAF 不是实际新内容屏幕 FPS，单位帧 CPU 减少不等于整机功率相同比例减少。

系统异常记录：daemon 的 NULL subclass 导致循环上传已用同 PID 单记录干预确认并规避；记录与一致备份保留，固件修复仍需小米。搜狗满核进入 CursorAnchorInfo/Xposed Hook，拒绝不可用接口后的末八个一秒样本均为 0 CPU 时间；HyperCeiler 作用范围未变。

历史 2026-10-07 / 早期 r3 测试保留在 evidence 和阶段文档，不能用旧的“默认 r2 / 候选 APK 未安装”描述当前设备。正式公开发行仍受 RELEASE-CHECKLIST 约束，当前是已部署的源码开发版本。
