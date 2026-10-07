# 当前验证状态

日期：2026-10-07。通用 GPU 开发栈已独立构建安装，并完成 Vulkan、OpenGL/Zink 和 Chromium 实际窗口验证。当前仍属于开发版。2026-10-07 已进一步完成现有应用入口与 Termux 新会话配置迁移。

## 已落地

- 验收前缀：`/opt/pad7spro-gpu-dev-20261007-r2`；`/usr/local/bin/gpu-run`、`/usr/local/bin/gpu-launcher` 指向该前缀。可选“GPU 应用启动器”保留在菜单；桌面现仅保留四个应用和 MySQL 启动。
- 通用入口支持 OpenGL、Vulkan、已识别 Chromium/Electron；未知程序接收标准硬件环境，不套用浏览器参数。支持明确的软件模式和实际 GPU PID 组件诊断。
- 修复 WSI 图像重复创建、临时 pNext、MAILBOX producer 同步、线程退出、oldSwapchain 退役并发及分配失败回收。
- 真实 BGRA 渲染图像与私有 RGBA AHB 分开：当前 X11 协议模式保持 BGRA 字节顺序进行 GPU copy，修复红蓝交换；公开图像及 view 的格式保持一致。
- 新入口默认 `PAD_GPU_MAX_FPS=60`，在 WSI 呈现端可取消地等待，不忙等；`120` 可选高刷新，`0` 可关闭此应用级上限。
- 分配器隔离补全别名检查，保留 Android 分配器以及 FILE/DIR 等成对管理；未适配的跨分配器 stdio 分配接口明确失败。

## 实机证据

- Vulkan 逻辑设备创建、真实指令提交、fence 与逐字内存读回通过。
- AHB 分配、写入、句柄发送/接收、释放发送端后读回与独立释放通过。
- native-color 模式下 RGBA/BGRA × FIFO/MAILBOX 各 50 次 oldSwapchain 替换、每轮 3 帧，真实退出码均为 0。之后针对当前 X11 的 BGRA 字节模式完成小范围呈现及真实 GLX/Chromium 验证。
- OpenGL 3.2/Zink 实际窗口运行，Android 截图中红/绿/蓝齿轮与 CPU 参考一致。
- Chromium 独立配置实例实际加载新前缀组件；WebGL 与 WebGL2 可用，renderer 为 ANGLE Vulkan/Mali-G925，红色像素读回 `[255,0,0,255]`，Android 实际画面同样为红色。
- 桌面入口通过非交互调用启动 `glxinfo -B`，返回 0。

结构化记录见 `evidence/development-2026-10-07.json`。原始日志/截图/短时 CPU 采样位于本机 `build/runtime-20261007*`。短时不同实际帧率的数据不能用于声称续航提升或固定功耗节省比例。

## 当前会话与边界

主基线/canary 的二进制库保留；旧 gpu-app.sh 已改为统一入口的兼容转发。Chromium、ChatGPT、Trae、CC Switch 的桌面、菜单、URL 和 XFCE 浏览器 helper 共 13 项已迁移，默认应用和 MIME 选择保持不变。Termux 实际 desktop-zink.sh 已同步，Widget 的 debian-zink 仍直接调用该脚本。用户随后关闭旧会话、从 Widget 启动并反馈正常；已读取新 XFCE 会话环境确认 r2、Zink、BGRA 和 60 FPS 默认值。这里指会话重启，不是 Android 整机重启。

当前 APK 仍为原有裁剪补丁版本；重启后的日常 X server 已带 `-max-fps 60`。显示节拍与 copy/fence 合并的同证书候选 APK 已生成并校验签名/16 KiB 对齐，但未安装；它是复用原资源的原生增量重打包，不是干净全量构建。切换会中断当前桌面，需保存工作后单独安排。见 `patches/termux-x11/README.md`。

Mesa 25.0.7 在该驱动上仍缺 `fillModeNonSolid`、`shaderClipDistance`。更高 OpenGL 特性、sRGB 表面、其他 WebKitGTK/Tauri 应用、视频硬解和长时间续航/休眠恢复仍需按实际需求适配。CPU 执行的业务逻辑和纯 CPU 绘制不会因启动器自动变成 GPU 工作。

## 软件适配交付

- Chromium：此前实际 WebGL/WebGL2、Mali、颜色与窗口验证通过；现有桌面/URL 入口已迁移。
- ChatGPT：独立配置实例约 5 秒，CDP 报告 ANGLE_VULKAN/Mali-G925、0 GPU 崩溃，新库映射稳定。
- Trae：最终独立配置实例约 8 秒，欢迎界面正常、新栈 GPU 稳定、0 GPU 崩溃。为 39 位 VA 下偶发早期 Oilpan cage 预留失败提供精确条件的一次容错；不改变 ASLR、V8、内存上限、用户 profile 或 GPU 参数。
- CC Switch：WebKit 实际 hardware policy getter=1、新栈 Mali 模块与正常窗口已确认；应用自身仍打印固定“已禁用”文字，该日志不代表实际 getter 状态。使用 WebKit 加速合成与 SHM 传输，并非端到端零拷贝。专用 glibc 适配在 Android 库装载前移除自己的 LD_PRELOAD，不应用于 Chromium/Electron。

本轮只做必要的启动/渲染短验收，未做登录、项目编辑或长时负载测试。设备迁移清单为 `evidence/desktop-migration-2026-10-07.json`。

## 本次开源更新

公开内容为桥接源码、固定依赖/完整补丁、启动和迁移工具、精简回归及结构化设备证据。实现流程见 [implementation.md](implementation.md)。不提交本机 build/out、测试 profile、原始截图/日志、APK/库二进制、签名密钥或厂商驱动。公开状态是功能可用的源码开发版；正式发行缺口见 [RELEASE-CHECKLIST](../RELEASE-CHECKLIST.md)。
