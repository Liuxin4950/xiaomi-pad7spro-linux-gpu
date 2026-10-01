# Termux:X11 GPU Present 补丁

上游：[termux/termux-x11](https://github.com/termux/termux-x11)。

固定基线：`d55f1b7e575de0a7d2b03c5882d5e3d375d01a4f`。

补丁：[termux-x11-gpu-popup-fix.patch](termux-x11-gpu-popup-fix.patch)，SHA-256：

```text
6af0f2604eb610d729fc70b8f90bf2fd63d5e22fa5aeb8af73fc13e7ad572f0e
```

## 修改内容

1. GPU Present 直接写 screen pixmap 时，将更新区域与窗口可见 clip 相交，避免覆盖上层候选框和菜单。
2. 对 redirected compositor pixmap 保留完整内容；临时 Region 在成功、回退及提前返回路径释放。
3. 添加 `-max-fps N`，范围 1–240，同时限制 X11 RandR mode 与真实 vblank 间隔。项目参考配置使用 60。
4. 将逐矩形 GPU copy 日志限制为调试模式，减少正常运行时的日志开销。

## 获取与应用

以下命令在 **Linux 构建环境** 中运行。先将本补丁保存到构建目录，保持其哈希不变：

```sh
git clone https://github.com/termux/termux-x11.git
cd termux-x11
git checkout --detach d55f1b7e575de0a7d2b03c5882d5e3d375d01a4f
git submodule update --init --recursive
git apply --check /absolute/path/termux-x11-gpu-popup-fix.patch
git apply /absolute/path/termux-x11-gpu-popup-fix.patch
git diff --check
```

子模块 revision 由固定提交的 gitlink 决定；不要更新到最新 HEAD。补丁修改顶层 `xserver.patch`，子模块本身还需由上游构建过程应用该补丁。

## 构建与签名

固定提交的 Gradle wrapper 使用 `gradle-9.8.0-all.zip`，模块包含 `lorie-app`。按该提交的构建配置准备兼容 JDK、Android SDK/NDK 后执行：

```sh
./gradlew :lorie-app:assembleDebug
```

以上是待在干净环境复核的构建入口。本轮只读取了固定提交的模块/Gradle 配置并做补丁检查，没有重新构建 APK；完整 JDK/SDK/NDK 版本和环境仍需补齐后才能标为已复现。

设备原构建记录写明 universal debug APK 的四种 ABI 编译成功，安装版本为 `1.03.01-d55f1b7-29.09.26`。原 APK 的 SHA-256 为 `cafaa567a76ebd08baa0115629b522ff58697b71738ef5a732b4a0b4da259bcf`。本草稿不包含 APK，也未在本轮重新核对其二进制哈希或签名。

自行构建的 APK 通常具有不同签名，不能假设它可以覆盖所有来源的现有安装。发布时给出签名证书指纹、升级/回退说明和设置备份方法；不发布签名私钥。

## 本轮验证

2026-10-01 从设备原补丁精确导出，哈希与设备及既有记录一致。取得固定基线的三个原始文件后，执行 `git apply --check --whitespace=error-all`，返回 0。该结果证明对这一基线可以应用，不等于已完成新 APK 构建和实机回归。
