#!/bin/sh
# Single daily GPU launcher for Chromium and Electron apps in the Debian chroot.
# trae uses the ANGLE Vulkan path (2026-09-28); do NOT go back to gl-egl: it SIGSEGVs on every launch.
set -eu

case "${1:-}" in
  chromium) app=Chromium; binary=/usr/lib/chromium/chromium ;;
  chatgpt) app=ChatGPT; binary=/usr/bin/chatgpt ;;
  trae) app=Trae; binary=/usr/share/trae-cn/trae-cn ;;
  *) printf 'usage: %s {chromium|chatgpt|trae} [app arguments]\n' "$0" >&2; exit 64 ;;
esac
shift

export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export HOME=/root TMPDIR=/tmp LANG=C.UTF-8
export DISPLAY="${DISPLAY:-:1}" XDG_RUNTIME_DIR=/run/user/0
export MESA_LOADER_DRIVER_OVERRIDE=zink GALLIUM_DRIVER=zink vblank_mode=0
export HYBRIS_LD_LIBRARY_PATH=/opt/mali-bridge/android-override:/apex/com.android.runtime/lib64/bionic:/system/lib64:/vendor/lib64:/vendor/lib64/hw
export VK_DRIVER_FILES=/opt/mali-bridge/share/vulkan/icd.d/sysvk_icd.json
unset LD_PRELOAD

log() {
  printf '[mali-gpu] %s\n' "$*" >&2
  printf '%s %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*" >> /tmp/mali-gpu-launch.log 2>/dev/null || true
}

if [ ! -x "$binary" ] ||
   [ ! -c /dev/binderfs/binder ] ||
   [ ! -d /dev/binderfs/binder_logs ] ||
   [ ! -r /opt/mali-bridge-canary/lib/libhybris-common.so.1 ] ||
   [ ! -r /opt/mali-bridge-canary/lib/libhybris/linker/q.so ] ||
   [ ! -r /opt/mali-bridge-canary/share/vulkan/implicit_layer.d/libVkLayer_window_system_integration.so ] ||
   [ ! -r "$VK_DRIVER_FILES" ]; then
  log "$app: Mali prerequisites missing; inspect binderfs and /opt/mali-bridge-canary"
  exit 78
fi

export LD_LIBRARY_PATH=/opt/mali-bridge-canary/lib
export VK_IMPLICIT_LAYER_PATH=/opt/mali-bridge-canary/share/vulkan/implicit_layer.d
log "$app: ANGLE Vulkan / Mali"
exec "$binary" \
  --no-sandbox --disable-gpu-sandbox \
  --use-gl=angle --use-angle=vulkan --enable-gpu --disable-software-rasterizer \
  --ozone-platform=x11 "$@"
