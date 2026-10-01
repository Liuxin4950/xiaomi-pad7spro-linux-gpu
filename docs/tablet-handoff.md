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

现有工作环境仍在 `/opt/mali-bridge` 和 `/opt/mali-bridge-canary`，Termux 日常入口保持现有配置。新独立安装在 `/opt/pad7spro-gpu`，目前有实例销毁故障，不能替换日常入口。详见 [验证状态](development-status.md)。

接手者优先读 `README.md`、`docs/development-status.md`、`docs/build.md` 和 `sources.lock.json`，再定位新旧 libhybris 的分配器/释放差异。不要把已识别 Mali 或构建成功当作整套运行通过。
