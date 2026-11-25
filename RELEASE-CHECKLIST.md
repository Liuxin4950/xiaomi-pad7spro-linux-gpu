# r3.6 发布检查（2026-11-11）

当前产物是 **r3.6-rc1，本机发布候选**，正式发布尚未完成。完整范围见 [发布说明](docs/r3.6-release.md)，部署见 [CURRENT-STATE](docs/CURRENT-STATE.md)。

- [x] X11 基线、子模块、0001–0017 补丁与 SHA-256 进入固定清单；本轮全新 native 对象构建。
- [x] APK 签名/对齐验证、同源 loader 与两个 CLI 包装脚本、构建/依赖报告。
- [x] 实际生产函数的拷贝、主帧、光标生命周期、空 state 与独立唤醒回归。
- [x] Termux HOME/PREFIX/rootfs 参数化；新 HOME 创建、幂等、参数转发、校验、冲突拒绝和失败回退测试。
- [x] 当前启动文件及 Clipman 格式修复同步，原件/权限/哈希保留；没有会话重启。
- [x] 当前状态/安装/维护文档收敛，历史全文保留；包内不带用户 profile、ADB key、厂商 Mali 或 Linux 二进制前缀。
- [x] 2026-11-25：锁定源码 aarch64 fresh build 并安装到独立 Linux r3.6 候选前缀；doctor、AHB 分配/读回/释放、Mali submit/readback、真实 X11 Vulkan swapchain 重建/Present 回归通过；Linux 全局入口已切换到隔离候选并留有备份；现存应用进程未重启。
- [ ] 候选 Linux 前缀上 CC Switch/Trae 实际 renderer、透明度、内容显示与交互验收。
- [ ] 用户报告的快速蓝牙鼠标跳动解决并验收；相对捕获效果尚未获认可。
- [ ] rc1 APK 在用户安排安全会话后替换；冷启动后核验前端/server 映射一致、休眠和回退。
- [ ] 新 Termux 保留 rootfs 的实际安装启动验证；当前只有隔离 HOME 测试。
- [ ] 干净设备/rootfs 的 OS4 复现，含 keepcaps 环境补丁完整源码和构建。
- [ ] 公开二进制对应源码/通知复核；修改版 bionic 对应源码和再分发范围仍未补齐。此次不打包 Linux 前缀。
- [ ] 如声称能效/稳定真实 120FPS，补同条件测量；当前没有这些声明。

代码提交已推送；未创建 tag 或公开 Release。APK 替换及任何桌面/X11 重启仍等用户安排安全时段；不得把文件名 final 当作已验收。
