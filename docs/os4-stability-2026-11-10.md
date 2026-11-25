# OS4：整帧冻结、锁屏清理与会话误清理（2026-11-10）

## 状态与操作边界

本次是系统升级后的稳定性修复，不是 r3.5 渲染优化续作。APK、Mali/WSI、gpu-run 默认后端均未更换；未开启 XFCE 合成器、切软件渲染、重启桌面/Termux、禁用系统服务或修改 SELinux。之前开启合成器曾导致全黑，不能把透明窗口黑块当作开启合成器的充分理由。

**已证实至少一次整帧冻结由 Android 冻结 Termux UID 引起；不声称所有历史卡顿都已归因，也不声称长期/锁屏稳定性已验收。**

## 1. 捕获到的真实故障链

2026-11-10 本地时间：

- 11:19:40.291 与 11:21:40.421，`dumpsys greezer` 记录 UID 10305 的 `FZ ... reason:ABNORMAL_MODE caller:32`，前面均有 `CPU_HIGH_LOAD`。
- 用户报告画面及光标一起停住时，X server PID 14325 的 cgroup v2 为 `/apps/uid_10305/pid_13766`。**父 UID 组** `cgroup.freeze=1`、`cgroup.events frozen=1`；叶组虽然 `cgroup.freeze=0`，也继承 `frozen=1`。ActivityManager 的 `isFrozen=false` 不足以排除这套厂商 UID 冻结。
- server 的 `latest_tick_ns` 停止，frame callback pending=1；copy 队列已排空，锁 owner=0。线程栈位于 `get_signal`，与冻结吻合，不是已证明的 Mali GPU hang。
- 11:20:05 X11 Android 前端 ANR：主线程在发送鼠标事件时阻塞于 socket `write` / `sock_wait_for_wmem`；暂停的 server 无法继续收取事件。
- 系统分别在 11:20:18.475、11:22:37.790 以 `widget_fg` 解冻。后台/小窗切换可能伴随解冻或 Surface 重建，不能只凭“改尺寸能恢复”断言驱动出错。
- 曾尝试只向该 UID 的 `cgroup.freeze` 写 0，但执行前已经是 0，**不能把那次恢复归功于这条命令**。没有部署循环写 cgroup 的保活程序。

设备本机 `/system_ext/framework/miui-services.jar` 的只读反汇编确认：

`handleCpuHighLoad` → `BigDataDynamicPolicyManager.notifyCpuHighLoadAppStatus` → `triggerHighCpuLoadFreeze` → `AurogonFilterManager.filter` → `freezeAction(...,32,"ABNORMAL_MODE",...)`。

过滤包含 `NO_RESTRICT_APP` 位；`AurogonImmobulusMode` 从 **Settings.System** 的 `MILLET_NO_RESTRICT_APP` 读逗号分隔、逐项 trim 的包名，并监听该设置变化。这是本设备实现证据，不是通用 Android API 契约；系统更新后须重查。

## 2. 已应用：补齐共享 UID 的包名豁免

**状态更正：本节上午的 Settings 写入只是临时派生值修补。14:55 再发时该项已消失，不能称为持久修复；下午改为应用省电 ContentProvider 的原始配置，见第 7 节。**

Termux `com.termux` 与 Widget `com.termux.widget` 共用 UID 10305。原不限制名单有 Termux、X11，但没有 Widget。系统包名获取实现存在从 UID 的包名数组取首项的路径；当时 `pm list packages --uid 10305` 顺序是 Widget、Termux。不能单凭顺序证明每次实际使用哪个包名，但遗漏共享 UID 包名是明确缺口。

11:28:42：保留 `MILLET_NO_RESTRICT_APP` 原字符串与所有其他应用，只追加 `com.termux.widget`。未改全局冻结开关、CPU 策略、云控或网络规则。

**实际效果证据**：`IGreezeManager.getAurogonCheckReason(10305)` 从 `fgservice|WIDGET_APP` 变成 `fgservice|WIDGET_APP|NO_RESTRICT_APP`；设置读回一致。不是只验证了写入成功。

注意：系统代码仍存在夜间深度静止场景对“不限制”应用的例外；此项不等于永久免除所有厂商省电策略。既有 Termux wake lock 不新增、不反复重拿；锁屏与长时验收仍须单独做。

回退：原值和修改值保存在本机私有 `build/os4-stability-20261110/no-restrict-change.json`。先确认当前值仍等于收据的 `after`，再通过 `settings --user 0 put system MILLET_NO_RESTRICT_APP <before>` 恢复；若已有其他人工修改，先合并，禁止整表覆盖。不运行网上来源不明的全局关闭省电/冻结脚本。

## 3. 锁屏退出是另一条已证实的链

Android `dumpsys activity exit-info com.termux.x11` 中 2026-11-09 18:38:00、20:50:05 为 `USER REQUESTED / FORCE STOP / LockScreenClean`，不是这两次都发生了 GPU/应用崩溃。其他条目有 `SwipeUpClean`、`OneKeyClean`，不可混算。

本次复核，Termux 和 X11 都已进入 ProcessManager 的实际锁定列表；已有 deviceidle 白名单与后台运行 appop 也在。不能只再让用户重复“锁后台”。**当前锁定是否已经阻止后续 LockScreenClean 尚未通过新的自然锁屏/恢复验证**；不主动关闭当前屏幕，也不为验证杀应用。

## 4. 已落盘、下次启动生效：会话观察失败不再误清理

OS4 更换 root 后，现有启动器经本机 ADB 进入无 app seccomp 的 root 上下文。旧 `run_session` 把 ADB 读 pidfile 失败与“会话已经退出”混淆，可能 break → EXIT cleanup → 结束仍在运行的桌面。它是代码层确认的风险，**没有把历史所有退出强归因于此**。

修补 `reference/termux/debian-shell.sh`：

- ADB 失败、空/不完整输出、读权限失败视为未知，保留会话；按 2/4/8/16/30 秒退避观察，不自动重启 ADB。
- 观察到存活后缓存 PID 与 `/proc/PID/stat` starttime，防 PID 复用与 pidfile 丢失。
- 只有两次成功探测一致确认 gone / wrong-root / reused 才结束等待。
- 初始 15 秒仍未确认启动只警告，不再因不可观测直接触发清理。代价是启动确实失败但拿不到 PID 时可能保持等待，用户保存工作后使用原显式停止入口。
- 原显式停止、owner 看门狗与正常退出清理契约不扩改。

已按当前文件哈希防漂移、备份原件并原子落盘到 Android：

- 文件：`/data/data/com.termux/files/home/debian-shell.sh`
- 备份：`/data/data/com.termux/files/home/.debian-shell.sh.before-os4-observation-20261110`
- 原 SHA-256：`7d9a4fcb55b04a0e4517c8eb06ee6f39fd54448f2752ac680f080386194daf00`
- 新 SHA-256：`0a397f314100869e3b2ab89412f17b30d2822ede6e3178cc843232263808c444`
- 保留 UID/GID 10305、0700、`security.selinux` xattr。未执行完整启动器、未重启当前 owner；**当前运行中的 launcher 仍使用旧函数，新函数下次正常启动才生效**。

仓库同时纳入已经在设备使用的 OS4 `debian-root.sh`，并把它加入原有桌面激活器文件映射，避免重部署丢失 root shim。其他 OS4 差异来自本机原文件快照，不是本次新增开关/服务策略；没有运行整套激活器覆盖全部入口。

回退脚本同样要核对当前新哈希，再以原子替换恢复备份并保留元数据；不必当场重启，也不能谎称回退已经改变运行中 bash 的函数。

## 5. 可重复、被动采样

`scripts/capture-x11-stall.py` 只支持哈希完全匹配的 r3.5 arm64 APK/native ABI。只读 `/proc/PID/mem` 与 cgroup 祖先；不 ptrace、不写内存、不注入输入、不截图、不重启/改图形配置。未知版本拒绝读取固定偏移。显式限制最多 1800 秒、输出必须是新私有目录；进程代际改变使采样失效。

在 chroot 内以 root 执行，例如：

```sh
python3 /opt/pad7spro-gpu-release-test/repository/scripts/capture-x11-stall.py \
  --seconds 120 --interval 1 \
  --output /opt/pad7spro-gpu-release-test/repository/build/x11-stall-NEW-UNIQUE
```

不要填写历史 PID。无 `--pid` 会重新发现唯一 server；存在歧义则退出。`--renderer-pid` 为可选，必须重新发现前端 PID；旧 ANR 前端 PID 不可继续使用。

判断两类数据：

1. UID/祖先 cgroup frozen=1 是系统冻结的直接证据，即使没有 draw_requested；读取失败是未知，不等于 thawed。
2. 持续 pending draw/copy 且帧计数不动是候选停滞，不把静态桌面当作故障。内部帧计数、Choreographer tick 不是屏幕真实内容 FPS。

修补后有界采样只能说明该时间段的状态；没有出现故障不等于完成锁屏、夜间、长期稳定性或流畅度验收。没有额外常驻监控/定时任务。

## 6. 验证与证据保存

- 修补后用户反馈“目前正常，还没再卡”。179 秒有界采样得到 179 个样本、内部帧计数前进 2170；所读的叶组、UID 父组、apps 祖先均为 0，没有 pending-work 候选。采样初版误把不提供 `cgroup.freeze` 的根 cgroup 也作为必读，导致聚合标记为 unknown（原始三层数据仍保留，不能改写旧样本）；已修正根组语义，额外 8 秒实机验证 8 个样本聚合结果均可读且未冻结。两段均不是物理 FPS、负载复现或长期验收。
- 全套 Python 单测 59 项通过，包含 ADB 断连/不完整回复/权限失败/确认退出、PID 复用、静态桌面不误判、父 UID 冻结识别。
- `bash -n` 两份 shell；真实 Android 只执行提取后的只读观察函数，返回 `alive:14471:7459484`。这是观察协议验证，不是重启/锁屏验收。
- 原始 Greezer、cgroup/栈、ANR、exit-info、系统代码快照、设置前后值、文件部署收据、采样及测试日志位于本机忽略目录 `build/os4-stability-20261110/`。含私有数据与厂商系统文件，不自动提交/发布。
- 黑块/透明窗口仍为独立未解决项；不以本次冻结证据证明 alpha 不支持，不再冒险开启合成器来验证。

## 7. 14:55 复发：修补原始省电配置，而不是反复写派生名单

用户未主动修改，输入提示词期间反复冻结。新现场 server PID 10116、前端 PID 5708，必须重新发现，不能沿用上午 PID。

- 14:50:18.840、14:52:18.980、14:54:19.142，以及 14:56:19.435 再有 `FZ:ABNORMAL_MODE`。复发采样直接读到父 UID `freeze=1/frozen=1`，不是只靠用户描述推测。
- 14:55 的 `MILLET_NO_RESTRICT_APP` 已无 Widget，Greezer 也不再报告其 `NO_RESTRICT_APP`。上午缺少原始配置同步，修补不完整；不能把写入时成功回读当作持久配置验收。
- 使用本机 PowerKeeper 注册的 ContentProvider **只读**查询发现：`com.termux` 的 `bgControl=noRestrict`，`com.termux.widget` 的 `bgControl=miuiAuto`。名单回退与原配置不一致相符；没有抓到实际覆盖动作的调用栈，因此不指定某次具体广播/进程为覆盖者。

14:56:54 起，通过 `content://com.miui.powerkeeper.configure/userTable`，仅对 `userId=0 AND pkgName="com.termux.widget"` 的现有一行将 `bgControl` 从 `miuiAuto` 更新为 `noRestrict`。没有直接编辑 SQLite、删行/插行、修改其他应用或系统分区。

结果：该行 `lastConfigured` 更新，读回 `bgControl=noRestrict`；**系统自行**把 Widget 写入 `MILLET_NO_RESTRICT_APP`，无需再手动写 Settings。随后 Greezer 的判定出现 `fgservice|NO_RESTRICT_APP`。

维护检查（Android root shell；只读）：

```sh
content query --uri content://com.miui.powerkeeper.configure/userTable \
  --where 'userId=0 AND pkgName="com.termux.widget"'
settings --user 0 get system MILLET_NO_RESTRICT_APP
dumpsys greezer
```

只看三层是否一致：应用原配置 `noRestrict` → 系统派生名单包含包名 → 实际 UID 策略识别 `NO_RESTRICT_APP`。以后若又丢失，先查原配置与系统日志，不部署循环覆写设置/解冻的常驻脚本。

独立回退这项改动时，先确认该行仍为本次 `noRestrict` 且没有新的人工调整，再通过相同 Provider、相同 user/package 条件恢复 `bgControl=miuiAuto`；让系统重新生成名单，不同时盲目恢复上午的整份 Settings 字符串。原始行、前后值和回读保存在私有 `build/os4-stability-20261110/recurrence-1455/provider-change.json`。

已按本设备服务实现核对 `thawUids` 后尝试仅解冻 UID 10305，caller 模块 32，reason `pad_gpu_user_recovery`，没有全局解冻或重启。**但调用前服务已报告 false，历史显示 14:57:28.619 由 `widget_fg` 解冻；不能把这次恢复归功于该调用。**

应用配置落盘、派生名单同步与策略识别已验证；跨后续高 CPU 检查、熄屏、系统重启、夜间与长期稳定性分别验收，不能合并成“已经彻底解决”。

15:00 复核：Provider 仍为 `noRestrict`，派生名单仍含 Widget，服务报告 `fgservice|NO_RESTRICT_APP`、`isUidFrozen=false`。修补后 150 秒采样（150 个样本）中父/叶/祖先组均可读，没有 frozen 或 unknown 样本，内部帧计数前进 1923；仅 43 个样本的 surface_available=1，因此不能把整段当作用户持续输入的窗口验收。采样已结束，不留下常驻监控。


## 2026-11-11 再现与局部恢复

鼠标修复换包期间，直接读到共享Termux UID10305父cgroup冻结，前端无法重连；Greezer保存21:25:51 ABNORMAL_MODE/CPU_HIGH_LOAD记录。正常切换Termux前台后系统解冻，回X11重连，server/XFCE未重启。Widget原配置又为miuiAuto且派生名单缺少Widget，说明昨日写入不能当作长期保持证明。本轮只恢复现有Widget noRestrict行，系统派生名单重新包含Widget，Greezer识别fgservice|NO_RESTRICT_APP。未部署解冻循环或禁用系统服务；仍需后续跨实际高CPU/重启验证。回执 `build/cursor-stutter-20261111/widget-policy-restored.json`，当前关联证据 `evidence/r3.6-cursor-independent-wake-2026-11-11.json`。冻结明确解释该次断连，但还不能归因为全部鼠标瞬移的原因。
