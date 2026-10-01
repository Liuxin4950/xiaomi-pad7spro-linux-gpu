# 平板接手

项目入口为 Debian 内 `/root/Working/xiaomi-pad7spro-linux-gpu`。该路径指向独立开发工作区 `/opt/pad7spro-gpu-release-test/repository`。

```sh
cd /root/Working/xiaomi-pad7spro-linux-gpu
git status
git pull --ff-only
```

源码缓存保存在 `build/sources`，完整构建记录和 stage 在 `build/runs`。有缓存时可以离线继续构建；`sources.lock.json` 固定依赖，GitHub 不可达时仍能继续本地修改。推送前先确认实际修改和验证结果：

```sh
git diff
git add <files>
git commit -m "Describe the verified change"
git push
```

现有工作环境仍在 `/opt/mali-bridge` 和 `/opt/mali-bridge-canary`，Termux 日常入口保持现有配置。新独立安装在 `/opt/pad7spro-gpu`，核心探针已通过，实际窗口回归尚未完成，暂不替换日常入口。详见 [验证状态](development-status.md)。

接手者优先读 `README.md`、`docs/development-status.md`、`docs/build.md` 和 `sources.lock.json`，再继续窗口回归、APK重建和方便的安装/回退流程。不要把已识别 Mali 或构建成功当作整套运行通过。

## 快捷核心检查

在 Termux 中，使用 KernelSU root 运行 Android 侧脚本（这是当前设备的物理路径）：

```sh
su -W -c "/system/bin/sh /data/linux/debian/opt/pad7spro-gpu-release-test/repository/scripts/android-probe.sh"
```

该脚本在私有挂载命名空间绑定现有 Android 资源，检查 Vulkan 与 AHB。最后出现 `GPU_CORE_PROBES_OK` 才表示两项通过，不等于桌面/功耗验收完成。其他 root 实现不支持 `-W` 时使用相应 su 参数。
