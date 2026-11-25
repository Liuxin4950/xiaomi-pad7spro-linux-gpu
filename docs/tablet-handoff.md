# 平板接手与回退

先读 [CURRENT-STATE](CURRENT-STATE.md) 获取唯一运行身份。本页只保留维护操作；研发历史在 [r3.6 记录](r3.6-development.md)，快捷配置在 [安装指南](setup.md)。

## 只读核对

```sh
readlink -f /usr/local/bin/gpu-run
cat /opt/pad7spro-gpu-fps-20261017/release.json
gpu-run doctor
```

Android 侧另取 `pm path com.termux.x11` 和实际 APK 哈希，分别核对前端、独立 X server 的 `/proc/PID/maps` / `map_files`。安装文件、前端、server、Linux 库是不同对象。重复打开单实例不会更新 server；不要抄历史 PID 或结构偏移。

## 入口

- Termux：`bash ~/debian-desktop.sh`；Widget：`debian-zink`，转发到相同入口；已有桌面只显示原会话。
- 正常图形应用经 `/usr/local/bin/gpu-run`，保留原参数与用户配置。
- 新 Termux 保留 rootfs 时按安装指南运行 bootstrap。只安装依赖和入口，不替换 APK或启动桌面。
- `debian-stop.sh` 无参数会停止整个 chroot 的全部应用；必须保存工作后才由用户运行。本轮没有执行。

## 备份和恢复

本轮启动原件与哈希：`build/r3.6-release-preparation-20261111/startup-backup/`、`startup-sync.json`。原子写入保留原 mode/owner/xattrs，已有进程未重启。

新 Termux 工具默认预览；`--apply --backup 新目录` 保存原件及恢复回执：

```sh
python scripts/configure-termux.py --restore /实际备份目录
python scripts/configure-termux.py --restore /实际备份目录 --apply
```

恢复先校验备份和用户后续修改；冲突时拒绝覆盖。能恢复旧文件、删除本次新建文件，不停止会话。

| APK 本机原件 | 路径 |
|---|---|
| 当前 X11 r3.6-rc1 | `build/r3.6-rc1-clean-20261111/candidate.apk`，SHA `b5f92532…`；当前安装与前端/server maps 一致 |
| 空 state 修复包 | `build/cursor-stutter-20261111/before-cursor-wake-installed.apk`（`cdee031c…`） |
| r3.5 备份 | `build/r3.6-research-20261110/rollback/installed-r35.apk` |
| 安装前 APK 备份 | `/opt/cc-switch-update-helper/backups/r3.6-x11-apk-20261125/installed-before.apk`，SHA `5aed7953…` |

当前设备已替换 APK；前端和 server 新 PID 均映射相同 rc1 APK。后续更换仍须核对证书、完整哈希和备份，并确认设备上的工作已保存。

Linux 回退把系统链接指回保留的完整前缀，正常重开目标应用，不覆盖映射中的库。r3.5 本地归档：`/opt/pad7spro-gpu-release-test/releases/r3.5-final-20261017/`。

## 故障定位

- 黑屏先区分没有 X server、未连接、Surface 生命周期或被冻结；ADB 失败不等于进程死亡。
- Greezer 检查父 UID cgroup 的 `cgroup.freeze` / `cgroup.events` 和日志。Widget `noRestrict` 曾回退，不能保证长期免冻结；不禁用服务或循环解冻。
- OS4 app seccomp：启动器通过本机 ADB、root、nsenter 在正确命名空间执行。新 Termux 无授权密钥时需批准新 ADB key；包内不带个人密钥。
- OS4 keepcaps shim 属已有 rootfs 环境补丁，源码/构建尚未完整纳入本仓库；新建 rootfs 不能假设已有此补丁。
- 相对捕获是当前诊断偏好，bootstrap 不默认开启。无收益时可在 X11 设置恢复 `pointerCapture=false`。
- Scene、Choreographer、rAF、WSI 与物理新内容计数不能互换；尚无稳定 120 FPS 和整机省电验收。

[整理前全文](history/2026-11-11-tablet-handoff-before-release-consolidation.md)。
