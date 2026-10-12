#!/system/bin/sh
# SPDX-License-Identifier: MIT
# Root Android-side preflight in a private mount namespace.
set -eu
rootfs=${PAD_GPU_ROOTFS:-/data/linux/debian}
prefix=${PAD_GPU_PREFIX:-}
case "$rootfs" in /data/*) ;; *) echo 'rootfs must be under /data' >&2; exit 64 ;; esac
case "$rootfs" in *[!a-zA-Z0-9_./-]*|*/../*|*/..) exit 64 ;; esac
if [ -n "$prefix" ]; then
case "$prefix" in /opt/*) ;; *) exit 64 ;; esac
case "${prefix#/opt/}" in ''|*/*|*[!a-zA-Z0-9_.-]*) exit 64 ;; esac
fi
[ "$(id -u)" = 0 ] || { echo 'Run this Android-side script using su' >&2; exit 77; }
if [ "${1:-}" != __inside ]; then
    exec /system/bin/unshare -m /system/bin/sh "$0" __inside
fi
[ -c /dev/mali0 ] || { echo 'Android Mali node missing' >&2; exit 78; }
[ -c /dev/binderfs/binder ] && [ -d /dev/binderfs/binder_logs ] || {
    echo 'Android existing binderfs instance missing' >&2; exit 78;
}
/system/bin/mount -o rprivate none /
for directory in dev proc sys system vendor apex; do
    /system/bin/mkdir -p "$rootfs/$directory"
    /system/bin/mount --rbind "/$directory" "$rootfs/$directory"
done
# Explicit binding prevents older child mounts from hiding the actual service instance.
/system/bin/mount --rbind /dev/binderfs "$rootfs/dev/binderfs"
if [ -z "$prefix" ]; then
    runner=$(/system/bin/chroot "$rootfs" /usr/bin/readlink -f /usr/local/bin/gpu-run)
    prefix=${runner%/bin/gpu-run}
    case "$prefix" in /opt/*) ;; *) echo 'Current GPU entry missing' >&2; exit 78 ;; esac
    case "${prefix#/opt/}" in ''|*/*|*[!a-zA-Z0-9_.-]*) exit 64 ;; esac
fi
/system/bin/chroot "$rootfs" /usr/bin/env -i \
    PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    HOME=/root TMPDIR=/tmp LANG=C.UTF-8 PAD_GPU_PREFIX="$prefix" \
    "$prefix/bin/gpu-run" probe
/system/bin/chroot "$rootfs" /usr/bin/env -i \
    PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    HOME=/root TMPDIR=/tmp LANG=C.UTF-8 \
    HYBRIS_LD_LIBRARY_PATH="$prefix/android-override:/apex/com.android.runtime/lib64/bionic:/system/lib64:/vendor/lib64:/vendor/lib64/hw" \
    "$prefix/bin/probe-ahb"
echo GPU_CORE_PROBES_OK
