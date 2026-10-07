#!/bin/bash
# SPDX-License-Identifier: MIT
set -euo pipefail
# The mock suite exercises native RGBA/BGRA semantics independently of the
# live desktop's legacy byte transport and per-application frame limit.
unset PAD_GPU_X11_COLOR_MODE PAD_GPU_MAX_FPS LD_PRELOAD LD_LIBRARY_PATH
if (($# != 3)); then
  echo 'usage: run-wsi-regression.sh PATCHED_WSI_SOURCE WSI_CMAKE_BUILD BRIDGE_DEPS_PREFIX' >&2
  exit 64
fi
source_dir=$(realpath "$1")
build_dir=$(realpath "$2")
deps_prefix=$(realpath "$3")
test_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
mapfile -d '' objects < <(find "$build_dir/CMakeFiles/VkLayer_window_system_integration.dir" -name '*.o' -print0)
((${#objects[@]})) || { echo 'Build the WSI layer first' >&2; exit 78; }
c++ -std=c++17 -O1 -g -pthread -rdynamic \
  -DVULKAN_WSI_LAYER_EXPERIMENTAL=0 -DWSI_IMAGE_COMPRESSION_CONTROL_SWAPCHAIN=0 \
  -I"$source_dir" -I"$build_dir" -I"$deps_prefix/include/android" \
  "$test_dir/wsi-regression.cpp" "${objects[@]}" "$build_dir/libwsi_x11.a" \
  -lxcb -lxcb-present -lxcb-xfixes -lxcb-dri3 -lX11-xcb -ldl \
  -o "$build_dir/wsi-regression"
timeout 15 "$build_dir/wsi-regression"
