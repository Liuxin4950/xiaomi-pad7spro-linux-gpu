#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Run in the new Termux, without su. Installs packages and files, never a desktop/APK.
set -Eeuo pipefail
[[ $(id -u) != 0 && -n ${PREFIX:-} ]] || { echo 'Run in Termux as its ordinary user, without su.' >&2; exit 77; }
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
command -v pkg >/dev/null || { echo 'Termux pkg is unavailable' >&2; exit 78; }
pkg install -y python coreutils procps util-linux pulseaudio android-tools x11-repo
pkg install -y termux-x11-nightly
backup="$HOME/.local/state/pad-gpu/termux-$(date +%Y%m%d-%H%M%S)-$$"
python "$script_dir/configure-termux.py" --rootfs "${1:-/data/linux/debian}" --apply --backup "$backup"
printf '\nConfigured. Backup: %s\nStart after saving and ending the old desktop: bash ~/debian-desktop.sh\n' "$backup"
