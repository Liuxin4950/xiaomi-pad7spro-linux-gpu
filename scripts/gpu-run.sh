#!/bin/bash
# SPDX-License-Identifier: MIT
set -Eeuo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
prefix=${PAD_GPU_PREFIX:-/opt/pad7spro-gpu}
[[ "$prefix" =~ ^/opt/[a-zA-Z0-9_.-]+$ ]] || exit 64
usage() { echo "usage: gpu-run {chromium|trae|chatgpt|electron BINARY|gl BINARY|probe} [arguments]" >&2; exit 64; }
mode=${1:-}; [[ -n "$mode" ]] || usage; shift
angle=0
case "$mode" in
  chromium) binary=/usr/lib/chromium/chromium; angle=1 ;;
  trae) binary=/usr/share/trae-cn/trae-cn; angle=1 ;;
  chatgpt) binary=/usr/bin/chatgpt; angle=1 ;;
  electron) binary=${1:-}; [[ -n "$binary" ]] || usage; shift; angle=1 ;;
  gl) binary=${1:-}; [[ -n "$binary" ]] || usage; shift ;;
  probe) binary="$prefix/bin/probe-vulkan" ;;
  *) usage ;;
esac
[[ -x "$binary" ]] || { echo "[pad-gpu] executable not found: $binary" >&2; exit 78; }
[[ -c /dev/mali0 ]] || { echo '[pad-gpu] /dev/mali0 unavailable; enter the mounted chroot' >&2; exit 78; }
for library in lib/libsysvk.so lib/libhybris-common.so.1 lib/libhybris/linker/q.so \
  lib/libahb-wrapper.so android-override/libc.so; do
  [[ -f "$prefix/$library" ]] || { echo "[pad-gpu] missing $library" >&2; exit 78; }
done
unset LD_PRELOAD LD_LIBRARY_PATH LIBGL_ALWAYS_SOFTWARE
export TMPDIR=/tmp LANG=C.UTF-8
export HYBRIS_LD_LIBRARY_PATH="$prefix/android-override:/apex/com.android.runtime/lib64/bionic:/system/lib64:/vendor/lib64:/vendor/lib64/hw"
export HYBRIS_VULKANPLATFORM=null
export VK_DRIVER_FILES="$prefix/share/vulkan/icd.d/sysvk_icd.json"
export VK_IMPLICIT_LAYER_PATH="$prefix/share/vulkan/implicit_layer.d"
export MESA_LOADER_DRIVER_OVERRIDE=zink GALLIUM_DRIVER=zink
if [[ "$mode" != probe ]]; then
  export DISPLAY=${DISPLAY:-:1} XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/0}
  [[ -c /dev/binderfs/binder && -d /dev/binderfs/binder_logs ]] || {
    echo '[pad-gpu] bind the existing Android binderfs instance before launching a GUI' >&2; exit 78;
  }
fi
arguments=()
if ((angle)); then
  [[ $EUID != 0 ]] || arguments+=(--no-sandbox)
  arguments+=(--disable-gpu-sandbox --use-gl=angle --use-angle=vulkan \
    --enable-gpu --disable-software-rasterizer --ozone-platform=x11)
fi
exec "$binary" "${arguments[@]}" "$@"
