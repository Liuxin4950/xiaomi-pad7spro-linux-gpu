# 复现与设备接入流程

更新：2026-10-07。固定源码构建、完整前缀安装和作者设备的日常入口迁移已实现；用户已从 Termux Widget 重启并确认桌面启动成功。本流程以已有 root chroot/XFCE 环境为起点，不是从 Android 原厂状态开始的全自动安装器。

## 前置环境

- 已取得 root 的 Xiaomi Pad 7S Pro；机型、固件范围见主 README。其他 GPU、固件和 proot 未据此获得支持结论。
- 已安装 Termux、Termux:X11 APK 与匹配的 Termux 侧组件，已有 Debian arm64 chroot 和 XFCE。
- chroot 能访问 `/dev/mali0`、Android 原有 binderfs，以及 `/system`、`/vendor`、`/apex` 等运行资源。不能在 chroot 新建空 binderfs 来替代原实例。
- 已有可运行的桌面启动、会话和清理脚本；作者设备 rootfs 为 `/data/linux/debian`、显示号 `:1`。准备新 rootfs、root 授权和 Android 策略不由桥接安装器代办。
- Chromium、ChatGPT、Trae、CC Switch 等应用由各自渠道安装；本项目安装的是桥接和适配组件，不包含这些应用。

当前应用以 root 运行，Chromium/Electron 使用 `--no-sandbox --disable-gpu-sandbox`。普通用户/sandbox 适配仍是独立工作。本机 SELinux 为 `Enforcing`，不把关闭 SELinux 列为已验证的安装条件。

## 1. 固定源码构建并安装独立前缀

在 Debian chroot 中按 [构建说明](build.md)准备依赖。选择尚不存在的专用前缀，不覆盖正在使用的目录；以下 `next` 仅是下一次构建的示例名字：

```sh
bridge_prefix=/opt/pad7spro-gpu-next
bash scripts/build.sh --prefix "$bridge_prefix" --jobs 4
bash scripts/install.sh "$(cat build/last-stage.txt)" "$bridge_prefix"
```

构建过程按 `sources.lock.json` 固定 Git revision、补丁和 bionic 哈希，在 stage 内完成构建。安装器检查完整组件、JSON 和前缀一致性，生成文件/符号链接清单，再写入专用前缀；已有目录会被拒绝。新安装不需要作者的旧主基线或 canary 库。

## 2. 在已挂载的桌面环境验证候选

保持日常系统链接不变，直接调用候选目录中的入口：

```sh
"$bridge_prefix/bin/gpu-run" doctor
"$bridge_prefix/bin/gpu-run" probe
"$bridge_prefix/bin/gpu-run" ahb
timeout --kill-after=2s 15s "$bridge_prefix/bin/gpu-run" vulkan \
  "$bridge_prefix/bin/probe-present" --cycles 3 --frames 3
```

`doctor` 是前置条件检查；两个核心探针验证实际设备提交/读回和 AHB 传输/释放；`probe-present` 创建真实 X11 窗口并重复呈现、销毁、重建交换链。检查真实退出码，不只看成功文字；外部超时用于约束异常驱动或清理等待。

随后按 [验证方法](validation.md)检查目标应用 renderer、实际库路径、GPU 进程稳定性、候选框/菜单和画面。Chromium/Electron 用全新测试 profile，Trae 再使用独立扩展目录，不替换正在使用的用户实例。短测不能替代 [功耗与稳定性对照](benchmarks.md)。

尚未运行桌面时，可在 Termux 使用作者设备已有的 Android root 条件检查核心链路，显式指定候选前缀：

```sh
su -W -c 'PAD_GPU_PREFIX=/opt/pad7spro-gpu-next /system/bin/sh /data/linux/debian/opt/pad7spro-gpu-release-test/repository/scripts/android-probe.sh'
```

以上物理路径属于作者设备。其他目录布局应改为自己仓库在 Android 根目录下的真实路径；其他 root 工具使用对应的 `su` 参数。该脚本使用私有 mount namespace 绑定现有 Android 资源，只验证核心探针，不测试 GUI。

## 3. 切换以后启动的应用入口

候选通过所需验收后，在 Debian 中切换两个系统链接：

```sh
ln -sfn "$bridge_prefix/bin/gpu-run" /usr/local/bin/gpu-run
ln -sfn "$bridge_prefix/bin/gpu-launcher" /usr/local/bin/gpu-launcher
/usr/local/bin/gpu-run info
```

当前作者设备这两个链接指向 `/opt/pad7spro-gpu-dev-20261007-r2`。前缀由入口自身推导，不在各应用图标中分别写库路径。切换链接影响以后启动的进程，已有进程继续使用已加载组件。

普通软件可继承新桌面的 GPU 环境直接启动；Chromium/Electron、WebKitGTK/Tauri 的入口选择见 [配置说明](configuration.md)。自定义 `.desktop` 时，已知应用的 `Exec` 可分别调用 `/usr/local/bin/gpu-run chromium %U`、`chatgpt %U`、`trae %F`、`cc-switch`，保留原图标和 URL/文件占位符。

## 4. 作者设备的既有入口迁移

`scripts/activate-desktop.py` 是作者设备的迁移工具，先预览再应用：

```sh
python3 scripts/activate-desktop.py
python3 scripts/activate-desktop.py --apply
```

它要求已安装并验证 `/usr/local/bin/gpu-run`，并要求作者原有兼容入口和 Termux 启动脚本存在。工具更新已知 `.desktop`、XFCE helper/面板入口、旧兼容转发脚本和 Termux 的 `desktop-zink.sh`，验证桌面文件并保留文件权限、所有者及可读的 SELinux 标签；不为干净 rootfs 创建完整桌面环境，也不改变默认浏览器/MIME 的选择。

作者设备已执行该迁移。Widget 的 `.shortcuts/debian-zink.sh` 继续调用 `~/mali-work/desktop-zink.sh`；该脚本经统一 GPU 入口启动 XFCE，并保留挂载、看门狗和既有会话复用逻辑。保存工作、正常结束旧会话后再从 Widget 启动，才采用新会话环境；用户已经完成这一步并确认成功。

全新设备应先配置适合自身路径和 root 工具的 Termux/chroot 会话，再参考 `reference/termux/` 接入统一入口；不能原样运行作者迁移脚本并宣称完成从零安装。

## 显示端与回退

当前继续使用已安装的、含既有 Present 裁剪/限帧改动的 Termux:X11 APK。本轮没有升级 APK；`0002` 显示端补丁只是候选。核心桥接安装、应用入口迁移和显示端 APK 部署是独立步骤，不能用候选源码推断设备已启用新显示端功能。

回退时将系统链接指回保留的、已核对的完整前缀，并在保存工作后正常重新建立会话。不要覆盖运行中库、强行替换活跃 mount namespace，或用全局进程清理代替应用回退。安装器目前不提供自动升级/卸载；`debian-stop.sh` 停止的是整个 chroot，不是桥接卸载器。

当前已完成作者设备构建/安装、四类应用短验收和 Widget 重启确认；干净同机型 rootfs 的端到端复现、长时导航/休眠恢复、同条件功耗和候选 APK 验收仍需独立记录。
