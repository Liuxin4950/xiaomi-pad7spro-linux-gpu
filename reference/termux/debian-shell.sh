#!/data/data/com.termux/files/usr/bin/bash
# Debian chroot 共享库 —— 以旧 ubuntu-shell.sh 为蓝本最小改动移植（2026-09-14）。
# 直接运行本文件 = 打开 root shell；`bash debian-shell.sh cmd` = 进容器跑 command-code（TUI）；
# 其他启动器 source 本文件复用挂载/会话/清理逻辑。
# 与旧版的差异仅三处：① 全 root（删 suid bind / 普通用户层；root 不受文件权限限制，
# 连带 socket chmod 666 等 workaround 也不再需要）② 看门狗按 /proc/PID/root 匹配全杀
# （旧版只杀会话进程组，setsid 逃逸守护进程会漏——修复"划掉 Termux 后持续耗电"）
# ③ 当前桌面入口统一由 mali-work/desktop-zink.sh 调用 gpu-run；不再设置旧 mesa_glthread / vblank_mode。
set -Eeuo pipefail

COMMON_SELF=$(realpath "${BASH_SOURCE[0]}")
# Installed beside this file; never source a file from the current directory.
[[ ! -f "$(dirname "$COMMON_SELF")/debian-gpu.conf" ]] || source "$(dirname "$COMMON_SELF")/debian-gpu.conf"
ROOTFS="${DEBIAN_ROOTFS:-/data/linux/debian}"
PREFIX_DIR="${DEBIAN_TERMUX_PREFIX:-${PREFIX:-/data/data/com.termux/files/usr}}"
# The Widget owns this runtime directory. Inherited TMPDIR may point to
# /data/local/tmp (unavailable inside the chroot) when launched via adb.
TMP_DIR="$PREFIX_DIR/tmp"
# 固定 Termux 自己拥有的音频运行目录，避免沿用旧的失效 runtime 软链。
export PULSE_RUNTIME_PATH="$TMP_DIR/debian-pulse"
MOUNT=/system/bin/mount
CHROOT=/system/bin/chroot
MOUNT_LOCK="$TMP_DIR/debian-mount.lock"
X11_PIDFILE="$TMP_DIR/debian-x11-$$.pid"
VIRGL_PIDFILE="$TMP_DIR/debian-virgl-$$.pid"
CURRENT_MODE=""
MODE_LOCK=""
AUX_PID=""
ROOT_SESSION_PID=""

say()  { printf '[debian] %s\n' "$*"; }
warn() { printf '[debian][warn] %s\n' "$*" >&2; }
die()  { printf '[debian][error] %s\n' "$*" >&2; exit 1; }
source "$(dirname "$COMMON_SELF")/debian-root.sh"

# Xiaomi Linux 自带的 Xwayland 占用全局 display :0。若这里也使用 :0，
# chroot 里的 X11 客户端会优先连到错误的服务器并报 Authorization required。
# Termux:X11 官方示例使用 :1；仍允许通过 DEBIAN_DISPLAY=:N 临时覆盖。
X11_DISPLAY="${DEBIAN_DISPLAY:-:1}"
[[ "$X11_DISPLAY" =~ ^:[0-9]+$ ]] || die "invalid DEBIAN_DISPLAY: $X11_DISPLAY (expected :N)"
X11_SOCKET="$TMP_DIR/.X11-unix/X${X11_DISPLAY#:}"
# 图形服务不能按进程名(-x)匹配: termux-x11 经 app_process 启动, comm 是 "main"
# 而非 "termux-x11"（2026-09-27 实测, 曾导致 start 检测失效 / stop 漏杀）; virgl 的
# comm 又被内核截断为 15 字符。统一改用锚定行首的 cmdline(-f) 匹配: 能命中服务自身
# argv[0], 又不会像裸 pkill -f 那样误杀 cmdline 里恰含同名字符串的 su/bash 包装
# 进程（项目记忆: bash-tool-pkill-f-gotcha）。
X11_SERVER_RE='^termux-x11( |$)'
VIRGL_SERVER_RE='^virgl_test_server'

safe_path() {
  [[ "$1" =~ ^/[[:alnum:]_.@%+,:=/-]+$ ]] || die "unsafe path: $1"
}

mounted() {
  root "awk -v t='$1' '\$2 == t { found=1 } END { exit found ? 0 : 1 }' /proc/mounts" \
    >/dev/null 2>&1
}

lock_mounts() {
  local owner n
  for n in $(seq 1 50); do
    if mkdir "$MOUNT_LOCK" 2>/dev/null; then
      printf '%s\n' "$$" > "$MOUNT_LOCK/pid"
      return
    fi
    owner=$(cat "$MOUNT_LOCK/pid" 2>/dev/null || true)
    if [[ ! "$owner" =~ ^[0-9]+$ ]] || ! kill -0 "$owner" 2>/dev/null; then
      unlink "$MOUNT_LOCK/pid" 2>/dev/null || true
      rmdir "$MOUNT_LOCK" 2>/dev/null || true
    fi
    sleep 0.1
  done
  die "another mount operation is still running"
}

unlock_mounts() {
  [[ "$(cat "$MOUNT_LOCK/pid" 2>/dev/null || true)" == "$$" ]] || return 0
  unlink "$MOUNT_LOCK/pid" 2>/dev/null || true
  rmdir "$MOUNT_LOCK" 2>/dev/null || true
}

mode_lock_path() {
  printf '%s/debian-%s.lock' "$TMP_DIR" "$1"
}

acquire_mode() {
  local mode="$1" lock owner_pid owner_start live_start
  lock=$(mode_lock_path "$mode")
  if mkdir "$lock" 2>/dev/null; then
    printf '%s %s\n' "$$" "$(awk '{print $22}' "/proc/$$/stat")" > "$lock/owner"
    MODE_LOCK="$lock"
    return 0
  fi

  read -r owner_pid owner_start < "$lock/owner" 2>/dev/null || true
  live_start=''
  [[ ! "$owner_pid" =~ ^[0-9]+$ ]] || \
    live_start=$(awk '{print $22}' "/proc/$owner_pid/stat" 2>/dev/null || true)
  if [[ -n "$live_start" && "$live_start" == "$owner_start" ]]; then
    return 1
  fi

  unlink "$lock/owner" 2>/dev/null || true
  rmdir "$lock" 2>/dev/null || return 1
  mkdir "$lock" || return 1
  printf '%s %s\n' "$$" "$(awk '{print $22}' "/proc/$$/stat")" > "$lock/owner"
  MODE_LOCK="$lock"
}

release_mode() {
  [[ -n "$MODE_LOCK" ]] || return 0
  local owner_pid owner_start
  read -r owner_pid owner_start < "$MODE_LOCK/owner" 2>/dev/null || true
  if [[ "$owner_pid" == "$$" ]]; then
    unlink "$MODE_LOCK/owner" 2>/dev/null || true
    rmdir "$MODE_LOCK" 2>/dev/null || true
  fi
  MODE_LOCK=''
}

begin_mode() {
  local mode="$1"
  acquire_mode "$mode" || die "$mode launcher is already running"
  CURRENT_MODE="$mode"
  trap cleanup_session EXIT INT TERM HUP QUIT
}

bind_once() {
  local source="$1" target="$2"
  mounted "$target" && return
  root "mkdir -p '$target' && '$MOUNT' --bind '$source' '$target'" \
    || die "mount failed: $source -> $target"
}

rbind_once() {
  local source="$1" target="$2"
  mounted "$target" && return
  root "mkdir -p '$target' && '$MOUNT' --rbind '$source' '$target'" \
    || die "mount failed: $source -> $target"
}

# Android 按 fork 时刻所在应用的 cpuset 给进程定核, 且之后永不改变:
# 小组件/后台态启动时整棵树会落在 background/foreground 等受限组,
# 永远用不到全部核心(htop 里几个核恒 0%), 桌面/浏览器极卡。
# 这里是 root: 建一个 0-9 全核专用组, 开工前把启动器自身放进去,
# 其后 fork 的子孙全部继承; cpuctl top-app 的调度加成照旧保留。
# 2026-09-28: 旧实现写 Android 的 top-app 组——该组被限制为 0-7(8 核),
# 两个 X925 大核(cpu8-9)永远拿不到; 且"promote→fork 会话"存在竞态窗口,
# Android 可能把启动器挪回受限组。改用专用组 + 会话内纠正(见 run_session)。
# 两个 cgroup 各自独立写入: 一个失败时另一个仍然生效, 告警也才准确。
promote_cgroup() {
  root "mkdir -p /dev/cpuset/debian 2>/dev/null; echo 0-9 > /dev/cpuset/debian/cpus 2>/dev/null; echo 0 > /dev/cpuset/debian/mems 2>/dev/null; echo $$ > /dev/cpuset/debian/tasks" \
    || warn 'cpuset promote failed; session may be limited to fewer CPU cores'
  root "echo $$ > /dev/cpuctl/top-app/tasks" \
    || warn 'cpuctl promote failed; scheduler shares may be reduced'
}

mount_all() {
  safe_path "$ROOTFS"
  safe_path "$TMP_DIR"
  [[ -d "$ROOTFS" ]] || die "rootfs not found: $ROOTFS"

  promote_cgroup
  lock_mounts
  root "mkdir -p '$ROOTFS/dev/pts' '$ROOTFS/dev/shm' '$ROOTFS/proc' '$ROOTFS/sys' '$ROOTFS/system' '$ROOTFS/apex' '$ROOTFS/sdcard' '$ROOTFS/tmp' '$ROOTFS/run/user/0'"
  bind_once /dev "$ROOTFS/dev"
  bind_once /proc "$ROOTFS/proc"
  bind_once /sys "$ROOTFS/sys"
  # 2026-10-30: /system 绑入，让容器内 root 进程可直接调用 /system/bin/{pm,am,logcat,dumpsys,...}
  # （会话经 su 启动，uid 0 / u:r:ksu:s0；pm install 等 root 操作可绕开 HyperOS 的 adb 安装限制）
  # 必须 rbind：hybrid_mount 在 /system/{app,priv-app,framework,etc/{sysconfig,permissions}} 有 overlay
  # 子挂载，普通 --bind 会丢；且 zink 入口随后见到已挂载会跳过它自己的 rbind（2026-10-30 实测）。
  rbind_once /system "$ROOTFS/system"
  # /system/bin/linker64 是指向 APEX 的软链，ART/libart 也在 APEX 里；普通 bind 不含子挂载，
  # 不 rbind /apex 的话 chroot 内执行 /system/bin/* 会 ENOENT（2026-10-30 实测）。
  rbind_once /apex "$ROOTFS/apex"
  # binderfs 是 /dev 的子挂载（--bind /dev 不会带进来）；/dev/binder -> /dev/binderfs/binder，
  # pm/am/dumpsys/settings 等 Android 命令全靠它（2026-10-30 实测）。
  [[ ! -d /dev/binderfs ]] || rbind_once /dev/binderfs "$ROOTFS/dev/binderfs"
  mounted "$ROOTFS/dev/pts" || root "'$MOUNT' -t devpts devpts '$ROOTFS/dev/pts'"
  mounted "$ROOTFS/dev/shm" || root "'$MOUNT' -t tmpfs -o size=256M,mode=1777 tmpfs '$ROOTFS/dev/shm'"
  [[ ! -d /sdcard ]] || bind_once /sdcard "$ROOTFS/sdcard"
  mkdir -p "$TMP_DIR"
  # $TMP_DIR 属主可能是 root（容器内 /tmp 即此目录, root 侧操作会改属主）,
  # 非属主 chmod 会 EPERM——非致命: 目录本身 1777 可写即可, 不能因此崩掉启动器。
  chmod 1777 "$TMP_DIR" 2>/dev/null || warn "chmod $TMP_DIR 失败(属主非本用户?), 继续"
  bind_once "$TMP_DIR" "$ROOTFS/tmp"
  root "chmod 700 '$ROOTFS/run/user/0'"
  # DNS 兜底: Android 无 resolv.conf, 容器内 glibc 需要; 缺/空则写公共 DNS
  root "[ -s '$ROOTFS/etc/resolv.conf' ] || printf 'nameserver 8.8.8.8\nnameserver 8.8.4.4\n' > '$ROOTFS/etc/resolv.conf'" \
    || warn 'resolv.conf 兜底写入失败, 进容器后请手动检查'
  unlock_mounts
  # debian_root_init already verified the local ADB transport. Do not restart
  # adbd again for a second, unrelated chroot ADB client during desktop startup.
}

# 看门狗在 owner 死后最多重试 5s 读 pidfile; 若 pidfile 只按 mode 命名, 它会
# 读到"重开后新会话"刚写的 pid 并把新会话杀掉(2026-09-11 实测)。带上 owner
# 后看门狗只认自己那一份, 竞态消失。
mode_pidfile() {
  printf '/run/user/0/debian-%s-%s.pgid' "$1" "$2"
}

write_session() {
  local mode="$1" body="$2" file
  file="$TMP_DIR/debian-$mode-session.sh"
  {
    printf '%s\n' '#!/bin/bash' 'set -Eeuo pipefail' 'export SHELL=/bin/bash'
    printf 'printf "%%s\\n" "$$" > %q\n' "$(mode_pidfile "$mode" "$$")"
    printf '%s\n' "$body"
  } > "$file"
  chmod 755 "$file"
}

start_watchdog() {
  local mode="$1" owner_start command
  owner_start=$(awk '{print $22}' "/proc/$$/stat")
  command="$PREFIX_DIR/bin/nohup $PREFIX_DIR/bin/bash '$COMMON_SELF' __watch '$$' '$owner_start' '$mode'"
  root "$command </dev/null >/dev/null 2>&1 &"
}

kill_mode() {
  local mode="$1" file pgid
  file="$ROOTFS$(mode_pidfile "$mode" "$$")"
  pgid=$(root "cat '$file' 2>/dev/null" || true)
  if [[ "$pgid" =~ ^[0-9]+$ ]]; then
    if root "[ \"\$(readlink /proc/$pgid/root 2>/dev/null)\" = '$ROOTFS' ]"; then
      root "kill -TERM -$pgid 2>/dev/null || true; sleep 1; kill -KILL -$pgid 2>/dev/null || true"
    elif root "[ -e /proc/$pgid ]"; then
      # 会话正常结束(进程已消失)属预期不告警; PID 还在但 root 不对才是异常
      warn "ignored stale $mode process-group file ($pgid)"
    fi
  fi
  root "unlink '$file' 2>/dev/null || true"
}

stop_pidfile() {
  local file="$1" expected="$2" pid command n
  pid=$(cat "$file" 2>/dev/null || true)
  if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
    command=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)
    if [[ "$command" != *"$expected"* ]]; then
      warn "ignored stale PID file $file (PID $pid is not $expected)"
      unlink "$file" 2>/dev/null || true
      return 0
    fi
    kill -TERM "$pid" 2>/dev/null || true
    for n in $(seq 1 20); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.1
    done
    kill -KILL "$pid" 2>/dev/null || true
  fi
  unlink "$file" 2>/dev/null || true
}

stop_graphics() {
  # 与 am start 同源限制：非 root uid 发 am 命令会被 SecurityException 拒绝
  root "/system/bin/am broadcast -a com.termux.x11.ACTION_STOP -p com.termux.x11" \
    >/dev/null 2>&1 || true
  stop_pidfile "$X11_PIDFILE" termux-x11
  stop_pidfile "$VIRGL_PIDFILE" virgl_test_server_android
  pkill -TERM -f "$X11_SERVER_RE" 2>/dev/null || true
  pkill -TERM -f "$VIRGL_SERVER_RE" 2>/dev/null || true
  pulseaudio --kill >/dev/null 2>&1 || true
  unlink "$X11_SOCKET" "$TMP_DIR/.X11-unix/X0" "$TMP_DIR/.virgl_test" \
    "$TMP_DIR/virgl_test_server" 2>/dev/null || true
}

cleanup_session() {
  local rc=$?
  trap - EXIT INT TERM HUP QUIT
  if [[ "$AUX_PID" =~ ^[0-9]+$ ]]; then
    kill "$AUX_PID" 2>/dev/null || true
  fi
  if [[ -n "$CURRENT_MODE" ]]; then
    kill_mode "$CURRENT_MODE"
    [[ "$CURRENT_MODE" != desktop ]] || stop_graphics
    unlink "$TMP_DIR/debian-$CURRENT_MODE-session.sh" 2>/dev/null || true
  fi
  if [[ "$ROOT_SESSION_PID" =~ ^[0-9]+$ ]]; then
    kill "$ROOT_SESSION_PID" 2>/dev/null || true
    wait "$ROOT_SESSION_PID" 2>/dev/null || true
  fi
  release_mode
  exit "$rc"
}

# BEGIN session observation (test-extracted; no source-time side effects)
# Sourced functions only. A failed ADB observation is NOT a dead desktop.
# No mounts, signals, process replacement, or automatic ADB restart here.

debian_session_status() {
  local file="$1" expected_pid="${2:-}" expected_start="${3:-}"
  safe_path "$file"
  safe_path "$ROOTFS"
  [[ -z "$expected_pid" || "$expected_pid" =~ ^[0-9]+$ ]] || return 74
  [[ -z "$expected_start" || "$expected_start" =~ ^[0-9]+$ ]] || return 74
  root "
    pid='$expected_pid'
    if [ -z \"\$pid\" ]; then
      [ -r '$file' ] || exit 74
      IFS= read -r pid < '$file' || exit 74
    fi
    case \"\$pid\" in ''|*[!0-9]*) exit 74 ;; esac
    if [ ! -d /proc/\$pid ]; then printf 'gone\\n'; exit 0; fi
    actual=\$(readlink /proc/\$pid/root) || exit 74
    start=\$(sed 's/.*) //' /proc/\$pid/stat | awk '{print \$20}') || exit 74
    case \"\$start\" in ''|*[!0-9]*) exit 74 ;; esac
    if [ -n '$expected_start' ] && [ \"\$start\" != '$expected_start' ]; then
      printf 'reused\\n'
    elif [ \"\$actual\" = '$ROOTFS' ]; then
      printf 'alive:%s:%s\\n' \"\$pid\" \"\$start\"
    else
      printf 'wrong-root\\n'
    fi
  "
}

debian_wait_for_session() {
  local file="$1" status confirmed failures=0 delay=1 expected_pid='' expected_start=''
  while :; do
    # Cache PID + /proc starttime after observing a live process. A vanished
    # pidfile or failed ADB observation must never be treated as a dead desktop.
    if status=$(debian_session_status "$file" "$expected_pid" "$expected_start"); then
      if [[ "$status" =~ ^alive:([0-9]+):([0-9]+)$ ]]; then
        expected_pid="${BASH_REMATCH[1]}"
        expected_start="${BASH_REMATCH[2]}"
        if (( failures )); then
          warn "session observation recovered after $failures failed probe(s); desktop preserved"
        fi
        failures=0
        delay=1
      elif [[ "$status" == gone || "$status" == wrong-root || "$status" == reused ]]; then
        if confirmed=$(debian_session_status "$file" "$expected_pid" "$expected_start") && [[ "$confirmed" == "$status" ]]; then
          warn "session exit confirmed by two successful probes: $status"
          return 0
        fi
        failures=$((failures + 1))
      else
        failures=$((failures + 1))
      fi
    else
      failures=$((failures + 1))
    fi
    if (( failures )); then
      if (( failures == 1 )); then
        warn 'session observation unavailable; NOT cleaning up the desktop (use debian-stop.sh only after saving work)'
      fi
      delay=$((delay < 16 ? delay * 2 : 30))
    fi
    sleep "$delay"
  done
}
# END session observation

run_session() {
  local mode="$1" body="$2" file pid n started=$SECONDS
  [[ -n "$CURRENT_MODE" ]] || CURRENT_MODE="$mode"
  write_session "$mode" "$body"
  start_watchdog "$mode"
  trap cleanup_session EXIT INT TERM HUP QUIT
  if [[ "$mode" == shell || "$mode" == cmd ]] && [[ -t 0 && -t 1 ]]; then
    root_tty "exec $CHROOT '$ROOTFS' /usr/bin/setsid /bin/bash /tmp/debian-$mode-session.sh"
    return $?
  fi
  # ADB 会阻塞到远端退出；后台等待保留原来的 PID 轮询、CPU 纠正和清理。
  root "exec $CHROOT '$ROOTFS' /usr/bin/setsid /bin/bash /tmp/debian-$mode-session.sh" &
  ROOT_SESSION_PID=$!
  # 依据会话 PID 文件等待和纠正 CPU 分组；ADB 客户端在后台传递输出。
  # 兼容 setsid/su 提前返回，且启动器退出时仍由原有清理和看门狗收尾。
  file="$ROOTFS$(mode_pidfile "$mode" "$$")"
  for n in $(seq 1 30); do          # 先等 pid 出现(会话启动失败的兜底)
    root "test -s '$file'" 2>/dev/null && break
    sleep 0.5
  done
  if ! root "test -s '$file'" 2>/dev/null; then
    # Transport failure and an absent PID file are ambiguous. Returning here
    # would run EXIT cleanup even if the desktop was actually started.
    warn "$mode startup not yet confirmed after 15s; preserving possible session and retrying observation (logs: $TMP_DIR)"
  fi
  # 2026-09-28: 会话起来后把 chroot 内全部进程收进全核 cpuset 并补 cpuctl。
  # 原因: "promote→fork 会话"存在竞态窗口, Android 可能把启动器挪回受限组
  # (实测会话整体落到 foreground/0-7); 一次性纠正后, 之后新开的应用都从
  # 已在组内的父进程继承。
  root "
    for entry in /proc/[0-9]*/root; do
      [ \"\$(readlink \"\$entry\" 2>/dev/null)\" = '$ROOTFS' ] || continue
      pid=\${entry#/proc/}; pid=\${pid%/root}
      echo \"\$pid\" > /dev/cpuset/debian/tasks 2>/dev/null || true
      echo \"\$pid\" > /dev/cpuctl/top-app/tasks 2>/dev/null || true
    done
  " || true
  debian_wait_for_session "$file"
  # 会话瞬间结束(dsh 崩溃、登录 shell 立即退出)时给可见提示, 不再静默返回 0
  if (( SECONDS - started < 3 )); then
    warn "$mode session ended within $((SECONDS - started))s; if that was not intended, check logs in $TMP_DIR"
  fi
}

unmount_one() {
  local target="$1" n=0
  while mounted "$target" && (( n < 32 )); do
    root "umount '$target' 2>/dev/null || umount -l '$target'" || break
    ((n+=1))
  done
}

terminate_all_chroot_processes() {
  safe_path "$ROOTFS"
  root "
    pids=''
    for entry in /proc/[0-9]*/root; do
      [ \"\$(readlink \"\$entry\" 2>/dev/null)\" = '$ROOTFS' ] || continue
      pid=\${entry#/proc/}; pid=\${pid%/root}; pids=\"\$pids \$pid\"
    done
    [ -z \"\$pids\" ] || kill -TERM \$pids 2>/dev/null || true
    sleep 1
    [ -z \"\$pids\" ] || kill -KILL \$pids 2>/dev/null || true
  "
}

unmount_all() {
  local target
  safe_path "$ROOTFS"
  lock_mounts
  # 除基础挂载外也清 zink 桥接(system/vendor/apex/dev/binderfs)和死掉的 portal
  # fuse 挂载; 桥接从 Android 共享挂载树 rbind 而来, 普通 umount 会 EBUSY,
  # 靠 unmount_one 自带的 umount -l 兜底摘除（2026-09-27 实测）。
  for target in dev/binderfs system vendor apex dev/shm dev/pts tmp sdcard run/user/0/doc dev proc sys; do
    unmount_one "$ROOTFS/$target"
  done
  unlock_mounts
}

show_status() {
  local foreign
  printf '%s\n' 'Mounts:'
  root "awk -v r='$ROOTFS/' 'index(\$2,r)==1 {print \"  \" \$2}' /proc/mounts" || true
  printf '%s\n' 'Processes:'
  root "for entry in /proc/[0-9]*/root; do [ \"\$(readlink \"\$entry\" 2>/dev/null)\" = '$ROOTFS' ] || continue; pid=\${entry#/proc/}; pid=\${pid%/root}; printf '  %s ' \"\$pid\"; tr '\\0' ' ' < /proc/\$pid/cmdline 2>/dev/null; echo; done" || true
  # 旧 Termux 世代的残留进程(每个 app 进程世代有独立 mount namespace):
  # 新会话的 unmount 够不到它们吊着的旧命名空间, 需用 debian-stop.sh 清杀
  foreign=$(root "cur=\$(readlink /proc/self/ns/mnt); n=0; for entry in /proc/[0-9]*/root; do [ \"\$(readlink \"\$entry\" 2>/dev/null)\" = '$ROOTFS' ] || continue; pid=\${entry#/proc/}; pid=\${pid%/root}; [ \"\$(readlink /proc/\$pid/ns/mnt 2>/dev/null)\" = \"\$cur\" ] || n=\$((n+1)); done; echo \$n" || true)
  if [[ "$foreign" =~ ^[0-9]+$ ]] && (( foreign > 0 )); then
    warn "$foreign chroot process(es) from an older Termux mount-namespace generation; run debian-stop.sh to clear them"
  fi
  printf 'X11(%s)=%s  VirGL=%s\n' "$X11_DISPLAY" \
    "$([[ -S "$X11_SOCKET" ]] && echo ready || echo off)" \
    "$([[ -S "$TMP_DIR/.virgl_test" ]] && echo ready || echo off)"
}

# Root-side fallback: survives Android killing the Termux UID, then cleans the whole
# chroot tree. 修正(2026-09-14): 不再只杀会话进程组——按 /proc/PID/root 匹配全杀,
# setsid 逃逸守护进程(xiccd/ssh-agent 等)也清掉; 修复"划掉 Termux 后持续耗电"。
watch_session() {
  local owner="$1" owner_start="$2" mode="$3" now file pgid n x11pid virglpid
  while [[ -r "/proc/$owner/stat" ]]; do
    now=$(awk '{print $22}' "/proc/$owner/stat" 2>/dev/null || true)
    [[ "$now" == "$owner_start" ]] || break
    sleep 2
  done

  # Desktop has a mode lock. If a newer owner replaced this session, its
  # watchdog must not kill the newer chroot. Shell/cmd retain legacy cleanup.
  if [[ "$mode" == desktop ]]; then
    file=$(mode_lock_path "$mode")
    [[ -r "$file/owner" ]] || return 0
    read -r pgid now < "$file/owner" || return 0
    [[ "$pgid" == "$owner" && "$now" == "$owner_start" ]] || return 0
  fi

  terminate_all_chroot_processes

  file="$ROOTFS$(mode_pidfile "$mode" "$owner")"
  unlink "$file" 2>/dev/null || true

  if [[ "$mode" == desktop ]]; then
    # 只认"自己那一份"实例化 pidfile: 不会误杀重开后新会话的 X11/virgl;
    # 文件已不存在 = cleanup_session 已收过尾, 也无需再碰全局 X11 app
    x11pid="$TMP_DIR/debian-x11-$owner.pid"
    virglpid="$TMP_DIR/debian-virgl-$owner.pid"
    if [[ -e "$x11pid" || -e "$virglpid" ]]; then
      /system/bin/am force-stop com.termux.x11 >/dev/null 2>&1 || true
      for file in "$x11pid" "$virglpid"; do
        pgid=$(cat "$file" 2>/dev/null || true)
        [[ "$pgid" =~ ^[0-9]+$ ]] && kill -KILL "$pgid" 2>/dev/null || true
        unlink "$file" 2>/dev/null || true
      done
    fi
  fi

  file=$(mode_lock_path "$mode")
  if [[ -r "$file/owner" ]]; then
    read -r pgid now < "$file/owner" || true
    if [[ "$pgid" == "$owner" && "$now" == "$owner_start" ]]; then
      unlink "$file/owner" 2>/dev/null || true
      rmdir "$file" 2>/dev/null || true
    fi
  fi
}

# Initialize once per launcher, including callers that probe chroot before mount_all.
debian_root_init

# When sourced, only expose the functions above.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  return 0
fi

if [[ "${1:-}" == __watch ]]; then
  [[ $# == 4 ]] || exit 2
  watch_session "$2" "$3" "$4"
  exit 0
fi

MODE="${1:-shell}"
case "$MODE" in
  shell)
    START_MSG='opening Debian root shell'
    SESSION_BODY='
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin TMPDIR=/tmp LANG=zh_CN.UTF-8 HOME=/root
exec /bin/bash -l'
    ;;
  cmd)
    # Command Code（command-code）TUI 模式（2026-09-15 新增, 按钮: .shortcuts/debian-cmd.sh）。
    # 与 shell 同构, 只是把登录 shell 换成代理 CLI；走 bash -l 是为了
    # 与"手动进 shell 再敲 command-code"完全同环境（/etc/profile.d/flutter.sh 等生效）。
    # --yolo = 跳过全部权限确认（别名 --dangerously-skip-permissions, 2026-09-15 用户要求设为默认）。
    START_MSG='opening Command Code (command-code --yolo)'
    SESSION_BODY='
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin TMPDIR=/tmp LANG=zh_CN.UTF-8 HOME=/root
cd /root
exec bash -lc "exec command-code --yolo"'
    ;;
  *)
    die "usage: bash $0 [shell|cmd]"
    ;;
esac

mount_all
if [[ "$MODE" == cmd ]]; then
  # 同 dsh 启动器：chroot 内查命令必须绝对路径（su 的 PATH 是 Android 的）
  root "chroot '$ROOTFS' /usr/bin/env PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin sh -c 'command -v command-code >/dev/null 2>&1'" \
    || die 'command-code is not installed in Debian container (npm i -g command-code)'
fi
termux-wake-lock 2>/dev/null || true
say "$START_MSG; use debian-stop.sh when all work is finished"
run_session "$MODE" "$SESSION_BODY"
