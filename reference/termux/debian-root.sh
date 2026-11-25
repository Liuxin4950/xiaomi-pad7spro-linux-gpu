#!/data/data/com.termux/files/usr/bin/bash
# OS4: 应用 su 继承 seccomp；通过本机 ADB 创建干净进程，再进入调用者挂载空间。
DEBIAN_ADB="$PREFIX_DIR/bin/adb"
DEBIAN_ADB_TARGET=127.0.0.1:15555
# Configured per Termux UID so reinstalling with a new UID does not inherit an
# old UID's OUTPUT firewall rejection on the previous ADB server port.
DEBIAN_ADB_PORT="${DEBIAN_ADB_SERVER_PORT:-5038}"
DEBIAN_ROOT_DIRECT=0

debian_adb() {
  "$DEBIAN_ADB" -P "$DEBIAN_ADB_PORT" "$@"
}

# Android sh 的单引号转义，保留多行、美元符号和命令里的引号。
debian_quote() {
  local value=${1//\'/\'\\\'\'}
  printf "'%s'" "$value"
}

debian_root_init() {
  local result n
  if [[ $(id -u) == 0 ]] && grep -qE '^Seccomp:[[:space:]]+0$' /proc/self/status; then
    DEBIAN_ROOT_DIRECT=1
    return 0
  fi
  [[ -x "$DEBIAN_ADB" ]] || die 'Termux needs android-tools: pkg install android-tools'
  # 先保证只允许本机访问，再打开 TCP；这些操作不需要 mount/chroot。
  su -c 'iptables -C INPUT -p tcp --dport 15555 ! -i lo -j DROP 2>/dev/null || iptables -I INPUT -p tcp --dport 15555 ! -i lo -j DROP' || die 'cannot protect local ADB (IPv4)'
  su -c 'ip6tables -C INPUT -p tcp --dport 15555 ! -i lo -j DROP 2>/dev/null || ip6tables -I INPUT -p tcp --dport 15555 ! -i lo -j DROP' || die 'cannot protect local ADB (IPv6)'
  # ADB server 本身不鉴权：独立端口只允许 Termux 的 UID 访问。
  local app_uid
  app_uid=$(id -u)
  su -c "iptables -C OUTPUT -o lo -p tcp --dport $DEBIAN_ADB_PORT -m owner ! --uid-owner $app_uid -j REJECT 2>/dev/null || iptables -I OUTPUT -o lo -p tcp --dport $DEBIAN_ADB_PORT -m owner ! --uid-owner $app_uid -j REJECT" || die 'cannot protect Termux ADB server (IPv4)'
  su -c "ip6tables -C OUTPUT -o lo -p tcp --dport $DEBIAN_ADB_PORT -m owner ! --uid-owner $app_uid -j REJECT 2>/dev/null || ip6tables -I OUTPUT -o lo -p tcp --dport $DEBIAN_ADB_PORT -m owner ! --uid-owner $app_uid -j REJECT" || die 'cannot protect Termux ADB server (IPv6)'
  # 复用本机 Debian 已授权的密钥，仅在 Termux 尚无密钥时复制；不输出密钥。
  mkdir -p "$HOME/.android"
  chmod 700 "$HOME/.android"
  if [[ ! -s "$HOME/.android/adbkey" ]]; then
    safe_path "$HOME"
    if su -c "test -s '$ROOTFS/root/.android/adbkey' && test -s '$ROOTFS/root/.android/adbkey.pub'"; then
      su -c "cp '$ROOTFS/root/.android/adbkey' '$HOME/.android/adbkey' && cp '$ROOTFS/root/.android/adbkey.pub' '$HOME/.android/adbkey.pub' && chown $(id -u):$(id -g) '$HOME/.android/adbkey' '$HOME/.android/adbkey.pub' && chmod 600 '$HOME/.android/adbkey'" || die 'cannot initialize local ADB key'
    else
      debian_adb start-server || die 'cannot create a local ADB key'
      say 'Approve this Termux ADB key in the Android authorization dialog.'
    fi
  fi
  if [[ $(su -c 'getprop service.adb.listen_addrs') != tcp:15555 ]] ||
     [[ $(su -c 'getprop init.svc.adbd') != running ]]; then
    su -c 'setprop service.adb.tcp.port 15555; setprop service.adb.listen_addrs tcp:15555; stop adbd; start adbd' || die 'cannot start local ADB bridge'
    sleep 2
  fi
  for n in {1..15}; do
    debian_adb connect "$DEBIAN_ADB_TARGET" >/dev/null 2>&1 || true
    result=$(debian_adb -s "$DEBIAN_ADB_TARGET" shell -T 'su -c "id -u; grep Seccomp: /proc/self/status"' 2>/dev/null || true)
    if [[ "$result" == $'0\nSeccomp:'* ]] && [[ "$result" =~ Seccomp:[[:space:]]+0 ]]; then
      return 0
    fi
    sleep 1
  done
  die 'local ADB root unavailable; re-enable temporary root and check ADB authorization'
}

debian_root_exec() {
  local tty="$1" command="$2" nested
  if [[ "$DEBIAN_ROOT_DIRECT" == 1 ]]; then
    /system/bin/sh -c "$command"
    return $?
  fi
  nested="exec /system/bin/nsenter -t $$ -m -- /system/bin/sh -c $(debian_quote "$command")"
  debian_adb -s "$DEBIAN_ADB_TARGET" shell "$tty" "su -c $(debian_quote "$nested")"
}

root() { debian_root_exec -T "$1"; }
root_tty() { debian_root_exec -tt "$1"; }
