# 已知界限与排查

更新：2026-10-12，当前 [r3.3](CURRENT-STATE.md)。

| 情况 | 已知事实 / 操作 |
|---|---|
| 入口已更新但旧应用未变 | 单实例仍复用旧主进程；保存工作后完整重开，查实际 renderer/Skia |
| X11 报 60 Hz 不代表实屏 60 张新画面 | 当前新 X server 已加载原生 tick 门控；WSI 上限仍保留，实际呈现需单独跟踪 |
| 单核满载或 idle 5 W | 独立测进程/线程；曾由搜狗 CursorAnchorInfo/Hook 忙循环造成，不把它直接归因于 Mali |
| daemon NullPointerException | 固件处理一条 NULL subclass 根事件不设防；已备份隔离，更新/新根事件可能复发 |
| 原生二维路径应用兼容问题 | `PAD_GPU_SKIA_BACKEND=angle` 是原来的 Mali 硬件路径；不自动切 CPU |
| WebKit | 有策略适配与 SHM 传输；不称端到端零拷贝，不向其注入 Electron 参数 |
| 显示颜色 / 菜单候选框遮挡 | 保持 BGRA 字节 Copy 与 X11 可见区域裁剪，不随意换 blit/剪裁 |
| 电流读数 / rAF / WSI 提交 | 不是长期续航或物理新画面 FPS，不能替代相同任务的完整对照 |
| 高版本 GL、sRGB、视频硬解 | 按真实能力检查；仍无全面支持承诺 |

没有改系统分区、SELinux 策略或原厂 Mali 驱动。不要冻结/卸载/禁用系统服务来掩盖瓶颈，不要整库恢复 daemon 旧备份，也不要用全局 pkill 来“修复”图形问题。
