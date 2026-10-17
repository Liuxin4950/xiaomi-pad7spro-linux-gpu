#!/data/data/com.termux/files/usr/bin/bash
# desktop-zink.sh — shared GPU desktop entry (2026-10-17).
# Widget 与 debian-desktop.sh 都转发到这里；名称保留兼容，不绑定某个旧前缀。
# XFCE/OpenGL 经 Zink，Chromium/Electron 的二维经 native Skia Vulkan，WebGL 经 ANGLE。
# 复用 debian-shell.sh 的挂载、看门狗和模式锁；已有 XFCE 只打开 X11，不重启。
# 更新 APK 后打开 Activity 不会重载独立 X server；切换须另行保存工作安排。
# 用法：bash ~/mali-work/desktop-zink.sh；停止整个 chroot 前先保存全部工作。
set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source /data/data/com.termux/files/home/debian-shell.sh

wait_socket() {
  local socket="$1" name="$2" n
  for n in $(seq 1 150); do
    [[ -S "$socket" ]] && return
    sleep 0.1
  done
  die "$name failed to start"
}

start_graphics() {
  local -a xargs=("$X11_DISPLAY" -ac -dpi "${X11_DPI:-120}" -max-fps "$X11_MAX_FPS")
  command -v termux-x11 >/dev/null || die 'termux-x11 is not installed'
  [[ "${X11_LEGACY_DRAWING:-0}" != 1 ]] || xargs+=(-legacy-drawing)

  if [[ ! -S "$X11_SOCKET" ]] || ! pgrep -f "$X11_SERVER_RE" >/dev/null 2>&1; then
    unlink "$X11_SOCKET" 2>/dev/null || true
    XDG_RUNTIME_DIR="$TMP_DIR" TMPDIR="$TMP_DIR" \
      nohup termux-x11 "${xargs[@]}" >"$TMP_DIR/debian-x11.log" 2>&1 &
    printf '%s\n' "$!" > "$X11_PIDFILE"
    wait_socket "$X11_SOCKET" Termux:X11
  fi
  root "/system/bin/am start --user 0 -n com.termux.x11/com.termux.x11.MainActivity" \
    >/dev/null 2>&1 || warn 'failed to bring Termux:X11 to front; open it manually'

  pulseaudio --start --exit-idle-time=-1 >/dev/null 2>&1 || true
  if ! pactl list short modules 2>/dev/null | grep -q module-native-protocol-tcp; then
    pactl load-module module-native-protocol-tcp \
      listen=127.0.0.1 auth-ip-acl=127.0.0.1 >/dev/null || \
      warn 'PulseAudio TCP module was not loaded'
  fi
}

if root "chroot '$ROOTFS' /usr/bin/pgrep -x xfce4-session >/dev/null 2>&1"; then
  root "/system/bin/am start --user 0 -n com.termux.x11/com.termux.x11.MainActivity" \
    >/dev/null 2>&1 || warn 'failed to bring Termux:X11 to front; open it manually'
  say 'XFCE is already running'
  exit 0
fi

# Only a new session adopts these settings; an existing desktop stays intact.
X11_MAX_FPS=${X11_MAX_FPS:-120}
[[ "$X11_MAX_FPS" =~ ^[0-9]{1,3}$ ]] && ((10#$X11_MAX_FPS >= 1 && 10#$X11_MAX_FPS <= 240)) \
  || die 'X11_MAX_FPS must be 1-240'
X11_MAX_FPS=$((10#$X11_MAX_FPS))
PAD_GPU_MAX_FPS=${PAD_GPU_MAX_FPS:-120}
[[ "$PAD_GPU_MAX_FPS" =~ ^[0-9]{1,3}$ ]] && ((10#$PAD_GPU_MAX_FPS <= 240)) \
  || die 'PAD_GPU_MAX_FPS must be 0 (uncapped) or 1-240'
PAD_GPU_MAX_FPS=$((10#$PAD_GPU_MAX_FPS))

begin_mode desktop
mount_all
if root "chroot '$ROOTFS' /usr/bin/pgrep -x xfce4-session >/dev/null 2>&1"; then
  die 'XFCE appeared during startup; refusing to create a duplicate session'
fi
root "chroot '$ROOTFS' /usr/bin/test -x /usr/local/bin/gpu-run" \
  || die 'unified GPU entry /usr/local/bin/gpu-run is missing from the chroot'

# ---- Mali bridge: Android 分区挂载（hybris 需要 /system /vendor /apex）----
# mount_all 已挂好 /dev；不要每次启动先 umount：若旧挂载仍被其他
# chroot 任务使用，强行摘除会让这些任务突然失去驱动文件。
say 'mounting Android partitions for the Mali bridge'
for m in system vendor apex; do
  mounted "$ROOTFS/$m" && continue
  root "mkdir -p '$ROOTFS/$m' && '$MOUNT' --rbind /$m '$ROOTFS/$m'" \
    || die "bridge mount failed: $m"
done

# ---- ANGLE Vulkan 通路需要 Android 已有的 binderfs 实例 ----
# binderfs 各挂载实例相互隔离：在 chroot 内 mount -t binder 得到的新实例没有
# Android 的服务节点，sysvk 取不到 AHB，Chromium 的 GPU 进程会崩溃。
# 只绑定 Android 已有的实例，绝不在 chroot 里 mount -t binder。
# 若已有挂载但没有 Android 的 binder_logs，则只告警；不要在启动时卸载
# 一个可能仍被使用的挂载。完整清理由 debian-stop.sh 执行。
if ! root "test -c /dev/binderfs/binder && test -d /dev/binderfs/binder_logs"; then
  warn 'Android binderfs source unavailable; Chromium/ChatGPT GPU launch is unavailable'
elif ! mounted "$ROOTFS/dev/binderfs"; then
  root "mkdir -p '$ROOTFS/dev/binderfs' && '$MOUNT' --rbind /dev/binderfs '$ROOTFS/dev/binderfs'" \
    || warn 'binderfs bind failed; Chromium/ChatGPT GPU launch is unavailable'
fi
if ! root "test -c '$ROOTFS/dev/binderfs/binder' && test -d '$ROOTFS/dev/binderfs/binder_logs'"; then
  warn 'chroot binderfs is not the Android instance; Chromium/ChatGPT GPU launch is unavailable'
fi

termux-wake-lock 2>/dev/null || true
start_graphics
say "GPU entry: /usr/local/bin/gpu-run (Skia Vulkan / ANGLE Vulkan / OpenGL Zink) on $X11_DISPLAY"
say "requested X11 max FPS=$X11_MAX_FPS; per-swapchain max FPS=$PAD_GPU_MAX_FPS"
say 'closing this session triggers cleanup'

run_session desktop "
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin TMPDIR=/tmp LANG=zh_CN.UTF-8 HOME=/root
export DISPLAY='$X11_DISPLAY'
export PULSE_SERVER=tcp:127.0.0.1:4713
unset LIBGL_ALWAYS_SOFTWARE LP_NUM_THREADS DEBIAN_LLVM_THREADS mesa_glthread vblank_mode PAD_GPU_PREFIX
export PAD_GPU_X11_COLOR_MODE=bgra PAD_GPU_MAX_FPS='$PAD_GPU_MAX_FPS' PAD_GPU_SKIA_BACKEND=native
export HYBRIS_VULKANPLATFORM=null
export XDG_RUNTIME_DIR=/run/user/0
export GTK_IM_MODULE=fcitx QT_IM_MODULE=fcitx XMODIFIERS=@im=fcitx SDL_IM_MODULE=fcitx
# gpu-run selects its own prefix, clears stale graphics variables, and passes the
# same BGRA/WSI contract to every child. Preserve the desktop's Chinese locale.
exec /usr/local/bin/gpu-run gl /usr/bin/env LANG=zh_CN.UTF-8 dbus-launch --exit-with-session startxfce4"
