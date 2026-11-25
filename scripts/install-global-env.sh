#!/bin/bash
# SPDX-License-Identifier: MIT
# Install a reversible login-shell hook for the selected bridge prefix.
set -Eeuo pipefail

usage() {
  echo 'usage: install-global-env.sh [--prefix /opt/prefix] [--apply --backup /absolute/new/backup-dir]' >&2
  exit 64
}

prefix=$(readlink -f -- /usr/local/bin/gpu-run)
prefix=${prefix%/bin/gpu-run}
apply=0
backup=
while (($#)); do
  case "$1" in
    --prefix) (($# >= 2)) || usage; prefix=$2; shift 2 ;;
    --apply) apply=1; shift ;;
    --backup) (($# >= 2)) || usage; backup=$2; shift 2 ;;
    *) usage ;;
  esac
done
[[ $EUID == 0 ]] || { echo 'Run inside the chroot as root' >&2; exit 77; }
[[ "$prefix" =~ ^/opt/[A-Za-z0-9_.-]+$ && -x "$prefix/bin/gpu-env" && -x "$prefix/bin/run-gpu" ]] || {
  echo 'prefix must contain executable bin/gpu-env and bin/run-gpu' >&2; exit 78;
}
prefix=$(realpath -e -- "$prefix")
target=/etc/profile.d/90-pad-gpu.sh
content=$(cat <<'EOF'
# Managed by pad-gpu; source the active bridge environment for Bash sessions.
if [ -n "${BASH_VERSION-}" ] && [ -r /usr/local/bin/gpu-env ]; then
  . /usr/local/bin/gpu-env
fi
EOF
)
if [[ -e $target || -L $target ]]; then
  [[ -f $target && ! -L $target ]] || { echo "refusing non-regular profile hook: $target" >&2; exit 73; }
  if [[ $(cat "$target") == "$content" ]]; then
    echo "already configured: $target prefix=$prefix"
    exit 0
  fi
  echo "refusing to replace existing profile hook: $target" >&2
  exit 73
fi
if ((!apply)); then
  printf 'would create %s for prefix %s\n' "$target" "$prefix"
  printf 'apply with --apply --backup /absolute/new/directory\n'
  exit 0
fi
[[ $backup == /* && ! -e $backup && ! -L $backup ]] || {
  echo '--apply requires a new absolute --backup directory' >&2; exit 64;
}
install -d -m 700 -- "$backup"
printf '%s\n' "target=$target" "created=true" "prefix=$prefix" > "$backup/receipt.txt"
temporary=$(mktemp /etc/profile.d/.90-pad-gpu.XXXXXXXX)
trap 'rm -f -- "$temporary"' EXIT
printf '%s\n' "$content" > "$temporary"
chmod 644 "$temporary"
chown root:root "$temporary"
mv -n -- "$temporary" "$target"
[[ -f $target && $(cat "$target") == "$content" ]] || { echo 'profile hook verification failed' >&2; exit 1; }
trap - EXIT
echo "installed $target; existing sessions are unchanged; backup receipt=$backup/receipt.txt"
