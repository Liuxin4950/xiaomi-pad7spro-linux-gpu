# 实现机制与流程

本文对应 2026-10-07 的源码开发更新，入口与依赖分别见 [配置](configuration.md)、[sources.lock.json](../sources.lock.json)。作者已从 Widget 重启会话并反馈正常；这不等于干净新 rootfs、长时负载或整机续航验收。

## 1. 固定源码到独立安装

`fetch-sources.py` 获取锁定的 libhybris、WSI、Android headers revision，以及有 SHA-256 的私有 libc。`build.sh` 导出独立源码副本、应用完整补丁、核对关键源码和分配器 hooks，再依次构建依赖、原生桥接和 WSI。

构建只输出 stage。`install.sh` 验证组件、manifest、文件哈希与内部符号链接后安装到尚不存在的专用 `/opt` 前缀；已有前缀会被拒绝覆盖。默认构建不包含 Android APK。切换 `/usr/local/bin/gpu-run` 的目标只影响以后创建的进程，已加载库不会热替换。

## 2. 会话和快捷方式

`reference/termux/desktop-zink.sh` 复用既有挂载、锁、看门狗和停止逻辑，绑定 Android 分区与原 binderfs，启动 X11，再经统一入口运行 XFCE：

```text
gpu-run gl → env LANG=zh_CN.UTF-8 → dbus-launch → startxfce4
```

因此普通子进程默认继承 Zink、ICD、WSI、BGRA 与帧率环境。`gpu-run` 会清理旧图形变量，检查当前前缀、Android 资源和本地 X11，然后选择后端：

| 路由 | 行为 |
|---|---|
| `auto` | 已知 Chromium/Electron 名称或 ICU+app bundle 布局使用 ANGLE Vulkan；未知程序仅设置环境；已知 CC Switch 使用 WebKit 路由 |
| `gl` / `vulkan` | 设置桥接环境，不加入浏览器参数 |
| `electron` / 应用别名 | 加入已验证的 ANGLE Vulkan/X11 参数，拒绝冲突参数 |
| `webkit` / `cc-switch` | X11、GPU 合成策略与 SHM 传输适配 |
| `--software` | 显式 llvmpipe/lavapipe 或应用软件模式，不依赖硬件失败后重试 |

`activate-desktop.py` 先生成迁移计划，验证已知 `.desktop` 后才按 `--apply` 更新。它保留 `%U` / `%F`、原应用参数、默认浏览器/MIME 选择及文件所有者、权限和可读取的 SELinux 标签。它只适用于作者已知目录布局，不安装任意新的 rootfs。

桌面现只保留四个应用入口与 MySQL 启动。可选 GPU 输入工具仍在菜单；它用参数数组执行程序并保存私有日志，不通过 shell 解释用户输入。

## 3. sysvk、AHB 和分配器

[`src/sysvk.c`](../src/sysvk.c) 用 `pthread_once` 打开 Android Vulkan HAL，转发 ICD 调度入口，并保留每进程 HAL 生命周期。它不伪造驱动特性或 OpenGL 版本。

[`src/ahb-wrapper.c`](../src/ahb-wrapper.c) 通过 libhybris 装载 `libnativewindow.so` 并一次性解析公开 AHardwareBuffer API；保留 Android DSO，避免 buffer 尚存活时卸载。glibc 客户端使用 [`ahb-api.h`](../src/ahb-api.h) 的公开 ABI 声明，不混入 bionic libc 头文件。

libhybris 补丁将 Android caller-owned 内存保留在 bionic 分配器，补齐 `scandir` 别名边界；FILE/DIR/addrinfo/locale 等 opaque handle 保留成对管理。尚未实现安全分配器桥接的 `getline/getdelim/open_memstream/open_wmemstream` 及 scanf `%m` 明确返回 `ENOSYS`。检查器覆盖全部 hook 表和别名，避免重新引入 glibc 分配、bionic 释放的错误。这些是明确的兼容性限制。

## 4. WSI 资源和 producer/consumer 同步

完整修正在 [`patches/wsi/0001-pad7spro-bridge.patch`](../patches/wsi/0001-pad7spro-bridge.patch)：

- 最终公共图像只创建一次，延迟分配时不替换已公开 handle；`pNext` 节点由 swapchain 持有。
- BGRA 使用真实 optimal 渲染图像和独立 RGBA AHB。仅在所需队列/格式能力可用时公开相应路径；不把实际 RGBA 图像假报成 BGRA。
- 当前 `bgra` 模式以 `vkCmdCopyImage` 保留公共 BGRA 图像的字节，匹配现用 Termux:X11 契约。`native` 开发模式的 RGBA/颜色 blit 路径不能用于未经改造的当前 X11。
- producer semaphore 等待、传输与 fence 同队列提交。FIFO worker 等完成；MAILBOX 在向 X11 呈现前也等待本帧 payload。
- 渲染/alias 图像具备必要 alias 标志；先等 fence，再释放命令池、图像、内存和 AHB 引用。
- 事件等待用 eventfd 取消，并始终 join。事件线程、旧链退役与释放统一锁序；condition wait 后重新获取数据指针，防止 Idle 先于 Complete 时访问已释放对象。
- 跨线程取消/错误状态使用原子变量；分配失败清理私有资源，保留已公开图像到析构。

当前应用级限帧在 X11 Present 之前使用 `steady_clock` 和 condition variable；取消能唤醒等待，暂停后不补发突发帧。默认每个 swapchain 60 FPS，可选择 120 或 0（不限制）。它不等于 WebKit 离屏渲染、所有 GPU copy 或整机工作的硬上限。

## 5. 两个应用专用处理

### WebKitGTK / CC Switch

CC Switch 会主动选择 WebKit 的 `NEVER` 策略，单纯设置 Zink 环境不足以开启其 GPU 合成。显式 WebKit 路由加载 [`webkit-gpu-policy.c`](../src/webkit-gpu-policy.c) 的 glibc 适配，调用真实 WebKitGTK 4.1 setter 选择 `ALWAYS`，并检查真实 getter；不可用时以 78 退出。

适配库在装载后移除自己的 `LD_PRELOAD`，不传给 libhybris 的 Android linker 或无关 helper；Chromium/Electron 不加载它。`WEBKIT_DISABLE_DMABUF_RENDERER=0` 保留加速合成，`WEBKIT_DMABUF_RENDERER_FORCE_SHM=1` 选择共享内存帧传输，避免假设 Android chroot 有标准 Linux GBM/DRM 设备。SHM 包含传输成本，不能称零拷贝。应用固定的“已禁用”日志会与真实策略冲突，应核对适配的 getter 结果和实际渲染。

### Trae 启动地址预留

在本机 39 位用户地址空间中，Trae 偶发在创建 GPU 之前出现精确 `Oilpan: CagedHeap reservation` 错误。它与 GPU 渲染失败不同。

[`trae-start.py`](../scripts/trae-start.py) 仅在最初 8 秒、精确错误、没有既有实例且尚未观察到 GPU/renderer/utility/JS 初始化时，最多再启一次。它保留 argv/profile，不修改 ASLR、V8、内存上限或 GPU 参数。启动期扫描限每 250ms，正常运行只转发输出/信号和退出码；清理限定到本次子树并验证 PID starttime，避免 PID 复用误伤。

## 6. 当前 APK 与候选显示优化

现用 X11 已有 screen 可见区域裁剪补丁，可保护菜单和候选框。原 `-max-fps` 改变 RandR 报告值，其 `vblank_interval` 没有参与实际调度。

第二阶段补丁增加 Choreographer 单调显示 tick 门控、合并过期 tick、paced flip 完成和正常 copy/root 共用 fence。已完成定向原生编译/链接和同证书原生增量 APK 验证，**没有安装到当前设备**。它不做静止内容去重，也不保证所有异步 GPU copy 都限频。细节见 [X11 补丁说明](../patches/termux-x11/README.md)。

## 验证范围

已有真实 Vulkan 提交/读回、AHB 往返、swapchain 重建、正确 RGB、Chromium WebGL1/2、ChatGPT/Trae/CC Switch 短启动及用户 Widget 重启反馈。短测数据和阶段性快照在 [evidence](../evidence/README.md)。冷 rootfs、长期输入/项目/导航、睡眠恢复、受控功耗、视频硬解和更高图形特性仍需独立验证。
