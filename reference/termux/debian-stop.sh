#!/data/data/com.termux/files/usr/bin/bash
# 运维脚本：无参 = 统一清理（杀光 chroot 进程含逃逸守护进程 + 停 graphics + 卸挂载
# + 清残留）；`status` = 查看状态；`backup` = 快照 rootfs 到 /sdcard/linux-backup/
# （需未挂载, 防"再次全灭"的保险）。
# 以旧 ubuntu-stop.sh 为蓝本最小改动移植（2026-09-14）：删 suid 树分支、加 backup。
set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=debian-shell.sh
source "$SCRIPT_DIR/debian-shell.sh"

do_backup() {
  local dest_dir="/sdcard/linux-backup" stamp out stage
  stamp=$(date +%Y%m%d-%H%M)
  out="$dest_dir/debian-base-$stamp.tar.gz"
  stage="$TMP_DIR/debian-base-$stamp.tar.gz"

  if mounted "$ROOTFS/dev" || mounted "$ROOTFS/proc" || mounted "$ROOTFS/tmp"; then
    die "rootfs 仍处于挂载状态, 请先运行 debian-stop.sh（无参）再备份"
  fi
  mkdir -p "$dest_dir" || die "无法创建 $dest_dir（检查 Termux 存储权限: termux-setup-storage）"

  # 清掉残留 socket：停机状态下均为死 socket；tar 无法归档 socket 类型，
  # 会告警并置非零退出码导致误判"打包失败"（2026-09-14 实测坑）
  root "chroot '$ROOTFS' /usr/bin/find / -xdev -type s -delete 2>/dev/null" \
    || warn 'socket 清理跳过（无碍，成功则归档更干净）'

  say "打包 $ROOTFS（可能几分钟, 请勿中断）..."
  root "tar -czf '$stage' -C '$(dirname "$ROOTFS")' '$(basename "$ROOTFS")'" \
    || die '打包失败'
  # tar 由 root 产生; $TMP_DIR 带 sticky 位, Termux 用户无法移动 root 属主文件——先归还属主
  root "chown $(id -u):$(id -g) '$stage'" || die '暂存文件属主归还失败'

  say "移动到 $out ..."
  mv "$stage" "$out" || die "移动到 /sdcard 失败（文件保留在 $stage）"
  ls -lh "$out"

  cat > "$dest_dir/RESTORE.md" <<EOF
# Debian chroot 备份恢复说明

快照: $(basename "$out")   生成时间: $(date "+%F %H:%M")

恢复步骤（Termux）:
1. sh ~/debian-stop.sh                      # 确保无进程、无挂载
2. su -c "rm -rf /data/linux/debian"        # 清掉当前 rootfs
3. su -c "mkdir -p /data/linux && tar -xzf /sdcard/linux-backup/$(basename "$out") -C /data/linux"
4. su -c "chown -R 0:0 /data/linux/debian"  # 统一属主（root-only 容器）
5. sh ~/debian-shell.sh                     # 冒烟: 能进 shell 即恢复成功

脚本全家（debian-*.sh）不在快照里, 需另备份或不删。
EOF

  say "backup done —— 快照与恢复说明都在 $dest_dir/"
}

case "${1:-}" in
  status) show_status; exit 0 ;;
  backup) do_backup; exit 0 ;;
  "")     ;;   # 无参 = 全量清理, 继续往下
  *)      die "usage: bash $0 [status|backup]" ;;
esac

say 'stopping all Debian chroot processes'
terminate_all_chroot_processes
# 清掉实例残留: 旧 session 脚本 / X11·virgl pidfile (launcher 被强杀时留下的);
# 上面已杀光 chroot 进程, 这里全量清除是安全的
rm -f "$TMP_DIR/debian-"*-session.sh "$TMP_DIR/debian-x11-"*.pid \
      "$TMP_DIR/debian-virgl-"*.pid 2>/dev/null || true
root "rm -f '$ROOTFS/run/user/0/debian-'*.pgid" 2>/dev/null || true
stop_graphics
unmount_all
# A mount that survives cleanup keeps device nodes and Android partitions
# visible to the next session. Report it instead of claiming a clean stop.
if root "awk -v r='$ROOTFS/' 'index(\$2,r)==1 { found=1 } END { exit found ? 0 : 1 }' /proc/mounts" \
    >/dev/null 2>&1; then
  warn 'some Debian mounts remain; run debian-stop.sh status before restarting'
fi
for mode in desktop dsh code; do
  lock=$(mode_lock_path "$mode")
  unlink "$lock/owner" 2>/dev/null || true
  rmdir "$lock" 2>/dev/null || true
done
termux-wake-unlock 2>/dev/null || true
say 'processes, graphics services and mounts are clean'
