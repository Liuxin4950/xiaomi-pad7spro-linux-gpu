# 新一轮 GPU / 平板融合：2026-11-10

用户重新提出继续改善适配、能效、流畅度与性能。允许开展新候选工作；r3.5 最终版仍为生产基线，本轮未部署库、替换 APK 或重启会话。工作区已有 OS4 稳定性及 probe-present 未提交改动均保留。

## 当前复核

- `gpu-run` 实际解析到 `/opt/pad7spro-gpu-fps-20261017/bin/gpu-run`，release.json 为 `r3.5-final-20261017`，doctor 前置检查通过。
- 本次 X server 命令仍为 `:1 -ac -dpi 120 -max-fps 120`。聊天应用 GPU 子进程实际映射 r3.5 WSI/sysvk/libhybris 与原厂 Mali Vulkan 库；这是映射证据，没有测本轮页面 FPS 或能耗。
- PowerKeeper Provider 的 Widget 原始行本次仍为 `bgControl=noRestrict`。这次读回不代替高负载、锁屏、夜间或重启后的稳定性验收。

## Writer 失败点有了调用栈证据

使用新建私有 profile、自建中英文测试文本和 `--view`，经 gpu-run 启动独立 Writer。只在该子进程加载诊断库，记录 PresentSelectInput 的参数和调用栈，不更改其行为。未访问用户原文档或原 profile，候选已退出。

记录到 `window=0`，调用链为：Skia 启用检查 → X11SkiaSalGraphicsImpl::createWindowContext → MakeGaneshVulkanForXlib → VulkanWindowContext::createSwapchain → 本项目 WSI → PresentSelectInput。现有 WSI 使用 unchecked 请求，错误可以送到应用的 Xlib 错误处理器。

对应版本 [LibreOffice X11 Skia 源码](https://github.com/LibreOffice/core/blob/libreoffice-25.2.3.2/vcl/skia/x11/gdiimpl.cxx) 的 createVulkanWindowContext 明确以 `None` 作为 drawable；[共享上下文实现](https://github.com/LibreOffice/core/blob/libreoffice-25.2.3.2/external/skia/share-grcontext.patch.1) 说明无实际窗口时只需创建共享 GPU context。下一步应修复应用侧无窗口上下文初始化，不应把窗口 0 替换成桌面 root 或任意用户窗口。

## 已构建、未部署的 WSI 防御候选

`patches/candidates/wsi-surface-loss.patch` 在 sources.lock.json 所锁定的 WSI commit 和全部 12 个 r3.5 补丁之后应用；未改最终版 lock 或默认发行配置。

1. 查询窗口几何失败返回 `VK_ERROR_SURFACE_LOST_KHR`，不再继续使用无效 extent；Capabilities2 原样传播错误。
2. 注册 Present 事件改用 checked 请求，在 WSI 内消费协议错误并返回 surface lost；失败时不创建事件线程。
3. 正常窗口的几何 extent、默认节拍和硬件路径保持原契约。

这是错误处理候选，**不代表 Writer 已启用 GPU**。没有把失败的 Writer 环境变量写进正常入口，也没有在候选测试中把 Writer 的自动 raster 回退算作适配成功。

## 验证

- 候选从锁定源码回放补丁后编译成功。候选 patch 的 reverse-check 通过。
- `tests/run-wsi-surface-loss-regression.sh SOURCE BUILD DEPS_PREFIX` 编译并运行 `wsi-surface-loss-regression.cpp`：原完整 WSI mock 回归通过，新增 geometry 丢失、Capabilities2 错误传播、Present 注册失败及无事件线程启动检查通过。
- `tests/wsi-surface-loss-live.c` 是刻意传 XCB_NONE 的负向健壮性探针，不是合法 Vulkan 用例示范。真实 Mali 下返回 `-1000000000`（surface lost），loader 日志确认实际加载候选库。
- 最终候选实际运行原已安装 probe-present，2 轮各 20 帧、BGRA、resize，通过 `VULKAN_SWAPCHAIN_RECREATE_PRESENT_OK`；实际 extent 为 256×192、240×176，loader 日志确认候选库，renderer 为 Mali-G925-Immortalis。这不是逐像素、物理 FPS 或功耗验收。
- 首次 mock 验证受继承 BGRA 环境和缺少物理属性 mock 影响而失败；最终 runner 按既有测试契约清理环境，候选在读取失败几何后立即返回，最终回归通过。失败日志保留。

## 文件与部署边界

本机私有产物目录：`build/writer-adaptation-20261110T150924Z/`。包含原始调用栈、隔离源码、构建产物、各轮日志、loader 日志和 candidate-identity.json。不自动公开原始日志。

- 候选 WSI SHA-256：`bd3d3bc24c31fb1ead3ec0e178f25787f8d06f74310dd33ff5515a06bc851d3e`
- 生产 WSI 复核仍为：`d011bb7b220ab83bfb7c136e1e1b3190def27c013cb24775167c405073d77636`

候选 manifest 只通过单次进程的 `VK_IMPLICIT_LAYER_PATH` 指向；系统链接、已映射库及普通启动入口未修改。无需生产回滚；测试进程已结束。

仍待完成：Writer 无窗口共享上下文的正确实现及真实窗口、中文、输入法、选择、缩放验收；之后才进行同负载滚动比较。能效需要同亮度/刷新率/后台负载下的有效对照，当前没有新增节能幅度、稳定 120 FPS 或输入延迟结论。
