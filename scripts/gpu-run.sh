#!/bin/bash
# SPDX-License-Identifier: MIT
set -Eeuo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Keep application/session settings, but discard a previous graphics stack.
clean_graphics_environment() {
  local name
  while IFS= read -r name; do
    case "$name" in
      LD_PRELOAD|LD_LIBRARY_PATH|VK_*|HYBRIS_*|MESA_*|GALLIUM_*|LIBGL_*|EGL_*|ZINK_*|ANGLE_*|DISABLE_WSI_LAYER|vblank_mode|__EGL_VENDOR_LIBRARY_*)
        unset "$name" ;;
    esac
  done < <(compgen -e)
}
clean_graphics_environment
launcher_path=$(readlink -f -- "${BASH_SOURCE[0]}")

log() { printf '[pad-gpu] %s\n' "$*" >&2; }
fail() { log "$*"; return 78; }
usage() {
  cat >&2 <<'USAGE'
usage: gpu-run [--software] [--headless] {auto|electron|webkit|gl|vulkan} BINARY [arguments]
       gpu-run [--software] {chromium|trae|chatgpt|cc-switch} [arguments]
       gpu-run {probe|ahb|info [GPU_PID]|doctor}
auto recognizes Chromium/Electron names or adjacent Electron application files.
Unknown programs receive the hardware environment without application arguments.
--software explicitly selects CPU rendering; hardware failures never retry in software.
--headless skips X11 checks for programs that do not create a window.
USAGE
  return 64
}

resolve_prefix() {
  if [[ -n ${PAD_GPU_PREFIX:-} ]]; then
    prefix=$PAD_GPU_PREFIX
  elif [[ ${launcher_path%/*} == */bin ]]; then
    prefix=${launcher_path%/bin/*}
  else
    # The repository copy is also useful before installing a new build.
    prefix=/opt/pad7spro-gpu
  fi
  [[ "$prefix" =~ ^/opt/[a-zA-Z0-9_.-]+$ && "$prefix" != /opt/. && "$prefix" != /opt/.. ]] || {
    log 'prefix must be a dedicated directory directly under /opt'; return 64;
  }
  prefix=$(realpath -m -- "$prefix")
  [[ "$prefix" =~ ^/opt/[a-zA-Z0-9_.-]+$ ]] || { log 'prefix resolves outside /opt'; return 64; }
}

application_binary() {
  case "$1" in
    chromium) printf '%s\n' /usr/lib/chromium/chromium ;;
    chatgpt) printf '%s\n' /usr/lib/chatgpt/ChatGPT ;;
    trae) printf '%s\n' /usr/share/trae-cn/trae-cn ;;
    cc-switch) printf '%s\n' /usr/bin/cc-switch ;;
    *) return 64 ;;
  esac
}

resolve_binary() {
  if [[ "$binary" != */* ]]; then
    binary=$(command -v -- "$binary") || { fail 'executable not found in Linux PATH'; return; }
  fi
  [[ -f "$binary" && -x "$binary" ]] || { fail "executable not found: $binary"; return; }
  binary=$(readlink -f -- "$binary")
  # Managed PATH shims must not recurse or lose an explicit --software mode.
  if [[ ${binary##*/} == gpu-entry-* || ${binary##*/} == codex-launcher ]]; then
    local first second
    { IFS= read -r first; IFS= read -r second; } < "$binary" || true
    case "$second" in
      '# pad-gpu entry: '*)
        managed_application=${second#\# pad-gpu entry: }
        binary=$(application_binary "$managed_application") || return
        [[ -x "$binary" ]] || { fail "managed executable missing: $binary"; return; }
        binary=$(readlink -f -- "$binary") ;;
    esac
  fi
}

is_angle_application() {
  case "${1##*/}" in
    chromium|chromium-browser|chrome|google-chrome|google-chrome-stable|electron|ChatGPT|chatgpt|trae-cn)
      return 0 ;;
    *) [[ ${1##*/} =~ ^electron[0-9]+$ ]] ;;
  esac
}

has_electron_distribution() {
  local directory=${1%/*}
  # Renamed Electron applications still ship ICU data and an application bundle.
  # A generic resources directory, or ICU data alone, also occurs in native apps.
  [[ -f "$directory/icudtl.dat" &&
     ( -f "$directory/resources/app.asar" || -f "$directory/resources/app/package.json" ) ]]
}

check_angle_arguments() {
  local argument
  for argument in "$@"; do
    if ((software)); then
      case "$argument" in
        --enable-gpu|--use-angle=*|--use-gl=*|--use-vulkan=*|--disable-software-rasterizer)
          fail "argument conflicts with --software: $argument"; return ;;
      esac
    else
      case "$argument" in
        --use-angle=vulkan|--use-gl=angle|--use-vulkan=native) ;;
        --use-angle=*|--use-gl=*|--use-vulkan=*|--disable-gpu|--disable-gpu-compositing|--disable-gpu-rasterization)
          fail "argument conflicts with the ANGLE Vulkan route: $argument"; return ;;
      esac
    fi
  done
}

check_install() {
  local component=$1
  command -v python3 >/dev/null || { fail 'python3 is required to validate bridge manifests'; return; }
  python3 - "$prefix" "$component" <<'PY'
import json, sys
from pathlib import Path
prefix, component = Path(sys.argv[1]), sys.argv[2]
errors = []
files = (['lib/libsysvk.so', 'lib/libhardware.so.2', 'lib/libhybris-common.so.1',
          'lib/libhybris/linker/q.so', 'lib/libahb-wrapper.so.1', 'android-override/libc.so']
         if component == 'core' else [])
for name in files:
    path = prefix / name
    if not path.is_file():
        errors.append('missing ' + str(path))
    elif not path.resolve().is_relative_to(prefix):
        errors.append('bridge dependency escapes prefix: ' + str(path))
try:
    if component == 'core':
        manifest = prefix / 'share/vulkan/icd.d/sysvk_icd.json'
        library = json.loads(manifest.read_text())['ICD']['library_path']
        expected = prefix / 'lib/libsysvk.so'
    else:
        manifest = prefix / 'share/vulkan/implicit_layer.d/VkLayer_window_system_integration.json'
        layer = json.loads(manifest.read_text())['layer']
        if layer['name'] != 'VK_LAYER_window_system_integration':
            raise ValueError('unexpected WSI layer name')
        library = layer['library_path']
        expected = prefix / 'share/vulkan/implicit_layer.d/libVkLayer_window_system_integration.so'
    target = Path(library)
    if not target.is_absolute():
        target = manifest.parent / target
    if not target.is_file() or target.resolve() != expected.resolve():
        errors.append('manifest points to wrong or missing library: ' + str(target))
    elif not target.resolve().is_relative_to(prefix):
        errors.append('manifest library escapes prefix: ' + str(target))
except (OSError, ValueError, KeyError, TypeError) as error:
    errors.append('invalid ' + component + ' manifest: ' + str(error))
for error in errors:
    print('[pad-gpu] ' + error, file=sys.stderr)
sys.exit(78 if errors else 0)
PY
}

check_android() {
  local need_binder=$1
  [[ -c /dev/mali0 && -r /dev/mali0 && -w /dev/mali0 ]] || {
    fail '/dev/mali0 unavailable or inaccessible; enter the mounted chroot'; return;
  }
  [[ -r /system/lib64/libnativewindow.so && -d /vendor/lib64 && -d /apex/com.android.runtime/lib64/bionic ]] || {
    fail 'Android system/vendor/apex resources are missing from this mount namespace'; return;
  }
  if ((need_binder)); then
    [[ -c /dev/binderfs/binder && -r /dev/binderfs/binder && -w /dev/binderfs/binder && -d /dev/binderfs/binder_logs ]] || {
      fail 'bind the existing Android binderfs instance before using AHB/GUI applications'; return;
    }
  fi
}

check_x11() {
  [[ "$DISPLAY" =~ ^:[0-9]+(\.[0-9]+)?$ ]] || {
    fail 'AHB/DRI3 requires a local X11 DISPLAY such as :1'; return;
  }
  [[ -d "$XDG_RUNTIME_DIR" && -w "$XDG_RUNTIME_DIR" ]] || {
    fail "runtime directory missing or unwritable: $XDG_RUNTIME_DIR"; return;
  }
  command -v xdpyinfo >/dev/null && command -v timeout >/dev/null || {
    fail 'install x11-utils and coreutils for the X11 connection check'; return;
  }
  timeout 3s xdpyinfo -display "$DISPLAY" >/dev/null 2>&1 || {
    fail "cannot connect to X11 $DISPLAY; start the desktop before launching applications"; return;
  }
}

configure_hardware() {
  # Installed Termux:X11 uses Xorg BGRA bytes inside RGBA gralloc buffers.
  case "${PAD_GPU_X11_COLOR_MODE:-bgra}" in bgra|native) ;; *) fail 'invalid X11 color mode'; return ;; esac
  export PAD_GPU_X11_COLOR_MODE=${PAD_GPU_X11_COLOR_MODE:-bgra}
  [[ "${PAD_GPU_MAX_FPS:-60}" =~ ^[0-9]{1,3}$ ]] && ((10#${PAD_GPU_MAX_FPS:-60} <= 240)) || {
    fail 'PAD_GPU_MAX_FPS must be 0 (uncapped) or 1-240'; return;
  }
  export PAD_GPU_MAX_FPS=${PAD_GPU_MAX_FPS:-60}
  # RandR's advertised refresh is not proof of an MSC/scanout cap. The old
  # installed X11 server still ticks at Android's rate, so retain the cap.
  export PAD_GPU_FIFO_DISPLAY_PACED=0
  export HYBRIS_LD_LIBRARY_PATH="$prefix/android-override:/apex/com.android.runtime/lib64/bionic:/system/lib64:/vendor/lib64:/vendor/lib64/hw"
  export HYBRIS_VULKANPLATFORM=null
  export VK_DRIVER_FILES="$prefix/share/vulkan/icd.d/sysvk_icd.json"
  export VK_IMPLICIT_LAYER_PATH="$prefix/share/vulkan/implicit_layer.d"
  export MESA_LOADER_DRIVER_OVERRIDE=zink GALLIUM_DRIVER=zink
}

configure_software() {
  local candidate
  export LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe
  # Exclude the bridge and other implicit layers, even if the desktop uses them.
  export VK_IMPLICIT_LAYER_PATH=/nonexistent/pad-gpu-software-layers
  export VK_DRIVER_FILES=/nonexistent/pad-gpu-software-icd.json
  for candidate in /usr/share/vulkan/icd.d/lvp_icd.json /usr/share/vulkan/icd.d/lvp_icd.aarch64.json; do
    if [[ -r "$candidate" ]]; then export VK_DRIVER_FILES="$candidate"; break; fi
  done
  if [[ "$mode" == vulkan && ! -r "$VK_DRIVER_FILES" ]]; then
    fail 'software Vulkan requires the Mesa lavapipe ICD (mesa-vulkan-drivers)'; return;
  fi
}

show_info() {
  printf 'prefix=%s\nicd=%s\nwsi=%s\n' "$prefix" \
    "$prefix/share/vulkan/icd.d/sysvk_icd.json" "$prefix/share/vulkan/implicit_layer.d/VkLayer_window_system_integration.json"
  if [[ -n ${1:-} ]]; then
    [[ "$1" =~ ^[1-9][0-9]*$ && -r /proc/$1/maps ]] || { fail 'provide a readable GPU process PID'; return; }
    python3 - "$1" <<'PY'
import sys
from pathlib import Path
paths = set()
for line in Path('/proc/' + sys.argv[1] + '/maps').read_text().splitlines():
    fields = line.split(None, 5)
    if len(fields) == 6 and any(name in fields[5] for name in
        ('libsysvk', 'libhybris', 'libhardware.so', 'libahb-wrapper', 'libVkLayer_window_system_integration',
         '/linker/q.so', 'vulkan.', 'libmali', '/android-override/libc.so')):
        paths.add(fields[5])
print('mapped_modules_pid=' + sys.argv[1])
print('\n'.join(sorted(paths)) if paths else '(no bridge modules mapped)')
PY
  else
    printf 'Configuration only; use info GPU_PID to inspect actual mapped modules.\n'
  fi
}

doctor() {
  local status=0 component library
  show_info
  for component in core wsi; do
    if check_install "$component"; then log "$component files/manifests: OK"; else status=78; fi
  done
  if check_android 1; then log 'Android device/resources: OK'; else status=78; fi
  if check_x11; then log "X11 connection $DISPLAY: OK"; else status=78; fi
  if command -v readelf >/dev/null; then
    for library in "$prefix/lib/libsysvk.so" "$prefix/lib/libhardware.so.2" \
      "$prefix/lib/libahb-wrapper.so.1" "$prefix/lib/libhybris-common.so.1" \
      "$prefix/lib/libhybris/linker/q.so" "$prefix/share/vulkan/implicit_layer.d/libVkLayer_window_system_integration.so"; do
      [[ -f "$library" ]] || continue
      printf '\nmodule=%s\n' "$library"
      if ! readelf -dW "$library" | sed -n '/NEEDED\|RPATH\|RUNPATH/p'; then status=78; fi
    done
  else
    log 'readelf unavailable; dependency/RUNPATH inspection skipped'
  fi
  log 'Doctor checks prerequisites without creating a GPU device; application rendering still requires verification.'
  return "$status"
}

main() {
  local mode binary angle=0 webkit=0 software=0 headless=0 requested_binary managed_application=
  local -a arguments=()
  while (($#)); do
    case "$1" in
      --software) software=1; shift ;;
      --headless) headless=1; shift ;;
      --help|-h) usage || true; return 0 ;;
      *) break ;;
    esac
  done
  mode=${1:-}; [[ -n "$mode" ]] || { usage; return; }; shift
  resolve_prefix || return
  export TMPDIR=/tmp LANG=C.UTF-8
  export DISPLAY=${DISPLAY:-:1} XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/$EUID}
  case "$mode" in
    info) (($# <= 1 && !software && !headless)) || { usage; return; }; show_info "${1:-}"; return ;;
    doctor) (($# == 0 && !software && !headless)) || { usage; return; }; doctor; return ;;
    chromium) binary=$(application_binary chromium); angle=1 ;;
    trae) binary=$(application_binary trae); angle=1 ;;
    chatgpt) binary=$(application_binary chatgpt); angle=1 ;;
    cc-switch) binary=/usr/bin/cc-switch; webkit=1 ;;
    auto|electron|webkit|gl|vulkan)
      binary=${1:-}; [[ -n "$binary" ]] || { usage; return; }; shift
      [[ "$mode" != webkit ]] || webkit=1
      [[ "$mode" != electron ]] || angle=1 ;;
    probe|ahb)
      ((!software)) || { usage; return; }
      headless=1
      if [[ "$mode" == probe ]]; then binary="$prefix/bin/probe-vulkan"; else binary="$prefix/bin/probe-ahb"; fi ;;
    *) usage; return ;;
  esac
  requested_binary=$binary
  resolve_binary || return
  if [[ "$mode" == auto && ${managed_application:-} == cc-switch ]]; then webkit=1; fi
  if [[ "$mode" == auto && ${binary##*/} == cc-switch ]]; then webkit=1; fi
  if [[ "$mode" == auto ]] && {
    is_angle_application "$requested_binary" || is_angle_application "$binary" || has_electron_distribution "$binary"
  }; then angle=1; fi
  if ((angle)); then check_angle_arguments "$@" || return; fi
  if ((software)); then
    configure_software || return
    if ((angle)); then
      [[ $EUID != 0 ]] || arguments+=(--no-sandbox)
      arguments+=(--disable-gpu --disable-gpu-compositing --ozone-platform=x11)
    fi
    log "explicit software rendering; executable=$binary"
  else
    check_install core || return
    if ((!headless)); then check_install wsi || return; fi
    if ((!headless)) || [[ "$mode" == ahb ]]; then check_android 1 || return; else check_android 0 || return; fi
    configure_hardware || return
    if ((angle)); then
      [[ $EUID != 0 ]] || arguments+=(--no-sandbox)
      arguments+=(--disable-gpu-sandbox --use-gl=angle --use-angle=vulkan \
        --enable-gpu --enable-gpu-rasterization --disable-software-rasterizer --ozone-platform=x11)
      case "${PAD_GPU_SKIA_BACKEND:-native}" in
        native)
          # Direct Vulkan for 2D raster/compositing; WebGL uses ANGLE Vulkan.
          local feature_list=Vulkan argument feature_options=1
          local -a remaining=()
          for argument in "$@"; do
            if ((feature_options == 0)); then remaining+=("$argument"); continue; fi
            case "$argument" in
              --) feature_options=0; remaining+=("$argument") ;;
              --enable-features=*) feature_list+=,${argument#*=} ;;
              --disable-features=*)
                if [[ ,${argument#*=}, == *,Vulkan,* ]]; then
                  fail 'Vulkan disabled while native Skia is selected; use PAD_GPU_SKIA_BACKEND=angle'; return
                fi
                remaining+=("$argument") ;;
              *) remaining+=("$argument") ;;
            esac
          done
          set -- "${remaining[@]}"
          arguments+=(--enable-features="$feature_list" --use-vulkan=native) ;;
        angle) ;;
        *) fail 'PAD_GPU_SKIA_BACKEND must be native or angle'; return ;;
      esac
    fi
    log "hardware environment; prefix=$prefix executable=$binary angle=$angle"
    log "ICD=$VK_DRIVER_FILES WSI=$VK_IMPLICIT_LAYER_PATH"
  fi
  if ((!headless)); then check_x11 || return; fi
  if ((webkit)); then
    export GDK_BACKEND=x11 CC_SWITCH_GDK_BACKEND=x11
    if ((software)); then
      export WEBKIT_DISABLE_COMPOSITING_MODE=1 WEBKIT_DISABLE_DMABUF_RENDERER=1
      unset PAD_GPU_WEBKIT_POLICY
    else
      [[ -r "$prefix/lib/libwebkit-gpu-policy.so" ]] || { fail 'WebKit GPU adapter missing'; return; }
      # Keep accelerated compositing, using WebKit's SHM transport instead of
      # assuming a Linux GBM/DRM device exists in this Android chroot.
      export WEBKIT_DISABLE_COMPOSITING_MODE=0 WEBKIT_DISABLE_DMABUF_RENDERER=0
      export WEBKIT_DMABUF_RENDERER_FORCE_SHM=1 PAD_GPU_WEBKIT_POLICY=always
      export LD_PRELOAD="$prefix/lib/libwebkit-gpu-policy.so"
    fi
  fi
  log 'Prerequisites passed; verify the target renderer and GPU PID after startup.'
  if ((angle)) && [[ ${binary##*/} == trae-cn ]]; then
    [[ -r "$prefix/bin/trae-start" ]] || { fail 'Trae startup adapter missing'; return; }
    exec /usr/bin/python3 "$prefix/bin/trae-start" "$binary" "${arguments[@]}" "$@"
  fi
  exec "$binary" "${arguments[@]}" "$@"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then main "$@"; fi
