#!/bin/bash
# SPDX-License-Identifier: MIT
# Common hardware GPU environment. Safe to source from login/XFCE sessions.

pad_gpu_env_prefix() {
  local source_path
  source_path=$(readlink -f -- "${BASH_SOURCE[0]}")
  if [[ -n ${PAD_GPU_PREFIX:-} ]]; then
    printf '%s\n' "$PAD_GPU_PREFIX"
  elif [[ ${source_path%/*} == */bin ]]; then
    printf '%s\n' "${source_path%/bin/*}"
  else
    printf '%s\n' /opt/pad7spro-gpu
  fi
}

pad_gpu_export_env() {
  local prefix name exported_names
  prefix=$(pad_gpu_env_prefix)
  [[ "$prefix" =~ ^/opt/[A-Za-z0-9_.-]+$ ]] || return 64
  prefix=$(realpath -m -- "$prefix")
  [[ "$prefix" =~ ^/opt/[A-Za-z0-9_.-]+$ ]] || return 64
  exported_names=$(compgen -e)
  while IFS= read -r name; do
    case "$name" in
      LD_PRELOAD|LD_LIBRARY_PATH|VK_*|HYBRIS_*|MESA_*|GALLIUM_*|LIBGL_*|EGL_*|ZINK_*|ANGLE_*|DISABLE_WSI_LAYER|vblank_mode|__EGL_VENDOR_LIBRARY_FILENAMES)
        unset "$name" ;;
    esac
  done <<< "$exported_names"
  export PAD_GPU_PREFIX="$prefix"
  export PAD_GPU_X11_COLOR_MODE=${PAD_GPU_X11_COLOR_MODE:-bgra}
  export PAD_GPU_MAX_FPS=${PAD_GPU_MAX_FPS:-120}
  export PAD_GPU_PRESENT_CLOCK=${PAD_GPU_PRESENT_CLOCK:-auto}
  export PAD_GPU_FIFO_DISPLAY_PACED=0
  export PAD_GPU_SKIA_BACKEND=${PAD_GPU_SKIA_BACKEND:-native}
  export HYBRIS_LD_LIBRARY_PATH="$prefix/android-override:/apex/com.android.runtime/lib64/bionic:/system/lib64:/vendor/lib64:/vendor/lib64/hw"
  export HYBRIS_VULKANPLATFORM=null
  export VK_DRIVER_FILES="$prefix/share/vulkan/icd.d/sysvk_icd.json"
  export VK_IMPLICIT_LAYER_PATH="$prefix/share/vulkan/implicit_layer.d"
  export MESA_LOADER_DRIVER_OVERRIDE=zink GALLIUM_DRIVER=zink
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  if [[ ${1:-} == --print ]]; then
    pad_gpu_export_env
    for name in PAD_GPU_PREFIX PAD_GPU_X11_COLOR_MODE PAD_GPU_MAX_FPS PAD_GPU_PRESENT_CLOCK \
      PAD_GPU_FIFO_DISPLAY_PACED PAD_GPU_SKIA_BACKEND HYBRIS_LD_LIBRARY_PATH \
      HYBRIS_VULKANPLATFORM VK_DRIVER_FILES VK_IMPLICIT_LAYER_PATH \
      MESA_LOADER_DRIVER_OVERRIDE GALLIUM_DRIVER; do
      printf '%s=%s\n' "$name" "${!name}"
    done
  else
    printf 'usage: source %s\n       %s --print\n' "$0" "$0" >&2
    exit 64
  fi
else
  pad_gpu_export_env
fi
