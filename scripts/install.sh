#!/bin/bash
# SPDX-License-Identifier: MIT
# Install a verified stage into a dedicated prefix; preserve existing installations.
set -Eeuo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export TMPDIR=/tmp
[[ $EUID == 0 ]] || { echo 'Run inside the chroot as root' >&2; exit 77; }
stage=${1:?usage: install.sh STAGE [/opt/pad7spro-gpu]}
prefix=${2:-/opt/pad7spro-gpu}
[[ "$prefix" =~ ^/opt/[a-zA-Z0-9_.-]+$ ]] || exit 64
stage=$(realpath "$stage")
source="$stage$prefix"
[[ -d "$source" && -f "$source/sources.lock.json" ]] || { echo 'Not a complete build stage' >&2; exit 78; }
for file in lib/libsysvk.so lib/libahb-wrapper.so lib/libhybris-common.so.1 lib/libhybris/linker/q.so \
  lib/libhardware.so android-override/libc.so share/vulkan/icd.d/sysvk_icd.json \
  share/vulkan/implicit_layer.d/libVkLayer_window_system_integration.so bin/probe-vulkan; do
  [[ -f "$source/$file" ]] || { echo "Missing stage file: $file" >&2; exit 78; }
done
python3 - "$source" "$prefix" <<'PY'
import hashlib, json, sys
from pathlib import Path
source=Path(sys.argv[1]); prefix=sys.argv[2]
manifest={'prefix':prefix,'files':{},'symlinks':{}}
for path in sorted(source.rglob('*')):
    relative=path.relative_to(source).as_posix()
    if path.is_symlink():
        if not path.resolve().is_relative_to(source.resolve()):
            raise RuntimeError('Symlink escapes installed tree: '+relative)
        manifest['symlinks'][relative]=str(path.readlink())
    elif path.is_file() and relative!='install-manifest.json':
        manifest['files'][relative]=hashlib.sha256(path.read_bytes()).hexdigest()
json.loads((source/'share/vulkan/implicit_layer.d/VkLayer_window_system_integration.json').read_text())
icd=json.loads((source/'share/vulkan/icd.d/sysvk_icd.json').read_text())
if icd['ICD']['library_path']!=prefix+'/lib/libsysvk.so':raise RuntimeError('Prefix differs from build')
(source/'install-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
PY
if [[ -e "$prefix" || -L "$prefix" ]]; then
  echo "$prefix already exists; refusing to overwrite. Verify or remove this project installation before upgrading." >&2
  exit 73
fi
temporary="/opt/.${prefix##*/}.install.$$"
[[ ! -e "$temporary" && ! -L "$temporary" ]] || exit 73
cp -a "$source" "$temporary"
mv -T "$temporary" "$prefix"
echo "INSTALL_OK prefix=$prefix"
