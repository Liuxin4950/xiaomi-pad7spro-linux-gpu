# 已知问题与兼容性边界

更新：2026-10-07。当前应用入口和会话已迁移到完整独立前缀，作者已从 Widget 重启并反馈正常。短时启动/渲染通过不代表所有负载都稳定。

| 项目 | 当前状态 | 后续方向 |
|---|---|---|
| 连续导航约 30 次后 `AllocateRingBuffer() failed` 或帧时间恶化 | 历史线索；新栈修复了具体资源/同步缺陷，但没有证明它们就是该症状根因 | 固定版本复测导航和长时负载，记录资源与 GPU 重建 |
| 更高 OpenGL / Vulkan 特性 | Mesa 25.0.7 在本机报告 OpenGL 3.2，仍缺 `fillModeNonSolid`、`shaderClipDistance` | 按真实能力判断应用，不伪造特性或版本 |
| sRGB swapchain | 当前未公开支持 | 单独实现并验证 gamma/传输语义 |
| WebKitGTK / CC Switch | 已通过专用路由短测；GPU 合成仍有 SHM 传输成本，WebGL2 未验证通过 | 输入法、编辑器和长时操作按实际需求继续验证 |
| 其他 WebKit/Tauri、AppImage 或自带渲染器 | 不在当前支持承诺内 | 确认框架和实际 renderer，必要时使用专用路由 |
| Trae Oilpan cage 预留失败 | 39 位 VA 下的早期启动问题；仅精确条件下有限容错一次，最终短启动通过 | 重复失败仍明确报错，不改 ASLR/V8 或自动重启运行中的应用 |
| 视频 Decode/Encode | 未接通硬解 | 与图形渲染分开适配和验证 |
| ChatGPT 在线内容 | 曾受网络/服务超时影响 | 与 GPU/窗口问题分开判断 |
| X11 菜单/候选框覆盖 | 已有可见区域裁剪补丁在作者设备验证 | 更换显示/桥接组件后保留遮挡、redirected pixmap 和输入回归 |
| 显示节拍与空闲功耗 | 应用 WSI 默认 60 FPS；原 APK 不提供第二阶段真实 tick 门控，也没有内容去重 | 单独验收候选 APK、帧时间和空闲策略 |
| root / Chromium sandbox | 当前 root chroot 配置使用禁用 sandbox 参数 | 普通用户和 sandbox 另行适配 |
| 新设备 / 固件 / proot / 冷 rootfs | 未完成全流程验证 | 先记录版本、权限与完整复现证据 |

旧主基线/canary 二进制库保留为历史工作基线。当前 `gpu-run` 选择一个完整前缀；若实际进程仍映射两套桥接组件，应检查入口和 RUNPATH，而不是把持有 `/dev/mali0` 当作成功。

已提供的源码与原生增量候选 APK 不构成正式 `v0.1.0` 发行。当前设备未安装第二阶段 APK；功耗/续航、休眠恢复和长期工作仍没有新版受控结论。见 [当前状态](development-status.md)及 [测量方法](benchmarks.md)。
