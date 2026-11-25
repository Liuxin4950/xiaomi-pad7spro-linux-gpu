#!/bin/bash
# SPDX-License-Identifier: MIT
# Friendly universal entry: run-gpu APP [ARGS] or run-gpu MODE APP [ARGS].
set -Eeuo pipefail
runner=$(readlink -f -- "${BASH_SOURCE[0]}")
prefix=${runner%/bin/*}
case "${1:-}" in
  auto|electron|webkit|gl|vulkan|probe|ahb|info|doctor|chromium|trae|chatgpt|cc-switch)
    exec "$prefix/bin/gpu-run" "$@" ;;
  --software|--headless)
    option=$1
    shift
    case "${1:-}" in
      auto|electron|webkit|gl|vulkan|probe|ahb|info|doctor|chromium|trae|chatgpt|cc-switch)
        exec "$prefix/bin/gpu-run" "$option" "$@" ;;
      *) exec "$prefix/bin/gpu-run" "$option" auto "$@" ;;
    esac ;;
  '') exec "$prefix/bin/gpu-run" doctor ;;
  *) exec "$prefix/bin/gpu-run" auto "$@" ;;
esac
