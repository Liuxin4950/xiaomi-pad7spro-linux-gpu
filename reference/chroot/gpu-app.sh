#!/bin/sh
# SPDX-License-Identifier: MIT
# Compatibility entry retained for old desktop files and external helpers.
set -eu
case "${1:-}" in
  chromium|chatgpt|trae|cc-switch) ;;
  *) printf 'usage: %s {chromium|chatgpt|trae|cc-switch} [arguments]\n' "$0" >&2; exit 64 ;;
esac
printf '%s app=%s route=/usr/local/bin/gpu-run\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$1" >> /tmp/mali-gpu-launch.log 2>/dev/null || true
exec /usr/local/bin/gpu-run "$@"
