#!/bin/bash
# SPDX-License-Identifier: MIT
set -Eeuo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export HOME=/root TMPDIR=/tmp LANG=C.UTF-8
unset LD_PRELOAD LD_LIBRARY_PATH
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
prefix=/opt/pad7spro-gpu
work="$repo/build"
jobs=4
while (($#)); do
  case "$1" in
    --prefix) prefix=${2:?missing prefix}; shift 2 ;;
    --work) work=${2:?missing work directory}; shift 2 ;;
    --jobs) jobs=${2:?missing job count}; shift 2 ;;
    *) echo "usage: $0 [--prefix /opt/pad7spro-gpu] [--work PATH] [--jobs N]" >&2; exit 64 ;;
  esac
done
[[ "$prefix" =~ ^/opt/[a-zA-Z0-9_.-]+$ ]] || { echo 'prefix must be a dedicated directory directly under /opt' >&2; exit 64; }
[[ "${prefix##*/}" != . && "${prefix##*/}" != .. ]] || { echo 'prefix must name a dedicated directory' >&2; exit 64; }
[[ "$jobs" =~ ^[1-9][0-9]*$ ]] || exit 64
[[ "$(uname -m)" == aarch64 ]] || { echo 'Build inside an arm64 Linux environment' >&2; exit 78; }
for command in python3 git make cmake autoreconf pkg-config gcc g++ readelf; do
  command -v "$command" >/dev/null || { echo "missing dependency: $command" >&2; exit 78; }
done
mkdir -p "$work/runs"
work=$(realpath "$work")
python3 "$repo/scripts/fetch-sources.py" --directory "$work/sources"
run=$(mktemp -d "$work/runs/build.XXXXXXXX")
stage="$run/stage"
deps="$stage$prefix"
mkdir -p "$deps" "$run/src"
python3 - "$repo" "$work/sources" "$run/src" <<'PY'
import hashlib, json, subprocess, sys
from pathlib import Path
repo, cache, source = map(Path, sys.argv[1:])
for item in json.loads((repo/'sources.lock.json').read_text())['git_sources']:
    target = source/item['name']; target.mkdir()
    archive = subprocess.Popen(['git','-C',str(cache/item['name']),'archive',item['commit']],stdout=subprocess.PIPE)
    extracted = subprocess.run(['tar','-xf','-','-C',str(target)],stdin=archive.stdout)
    archive.stdout.close()
    if extracted.returncode or archive.wait(): raise RuntimeError('Source export failed')
    subprocess.run(['git','init','--quiet',str(target)],check=True)
    for patch in item.get('patches',[]):
        subprocess.run(['git','apply','--check',str(repo/patch['path'])],cwd=target,check=True)
        subprocess.run(['git','apply',str(repo/patch['path'])],cwd=target,check=True)
    for relative, expected in item.get('verify_files',{}).items():
        if hashlib.sha256((target/relative).read_bytes()).hexdigest()!=expected:
            raise RuntimeError('Post-patch source checksum mismatch: '+item['name']+'/'+relative)
    if item['name']=='libhybris':
        subprocess.run([sys.executable,str(repo/'scripts/check-libhybris-hooks.py'),
                        str(target/'hybris/common/hooks.c')],check=True)
    print(item['name']+': patched source verified',flush=True)
PY
make -C "$run/src/android-headers" PREFIX="$prefix" DESTDIR="$stage" install
export PKG_CONFIG_PATH="$deps/lib/pkgconfig:/usr/lib/aarch64-linux-gnu/pkgconfig:/usr/share/pkgconfig"
export CFLAGS='-O2 -fPIC -Wa,--noexecstack'
export CXXFLAGS='-O2 -fPIC -Wa,--noexecstack'
export LDFLAGS="-Wl,-z,nodelete -Wl,-z,noexecstack -Wl,-rpath,$prefix/lib"
cd "$run/src/libhybris/hybris"
NOCONFIGURE=1 ./autogen.sh
./configure --build=aarch64-linux-gnu --with-android-headers="$deps/include/android" \
  --with-default-hybris-ld-library-path="$prefix/android-override:/apex/com.android.runtime/lib64/bionic:/system/lib64:/vendor/lib64:/vendor/lib64/hw" \
  --enable-property-cache --enable-experimental --enable-arch=arm64 \
  --enable-mali-quirks --disable-adreno-quirks --enable-glvnd --prefix="$prefix" --libdir="$prefix/lib"
make -j"$jobs"
make DESTDIR="$stage" install
# The glibc Vulkan loader must remain the system loader. Do not ship hybris' loader shim.
python3 "$repo/scripts/prune-stage-vulkan-shim.py" "$stage" "$prefix"
cmake -S "$repo" -B "$run/native-build" -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$prefix" -DBRIDGE_DEPS_PREFIX="$deps" \
  -DCMAKE_SHARED_LINKER_FLAGS="-Wl,-rpath-link,$deps/lib"
cmake --build "$run/native-build" -j"$jobs"
DESTDIR="$stage" cmake --install "$run/native-build"
cmake -S "$run/src/wsi" -B "$run/wsi-build" -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DCMAKE_INSTALL_PREFIX="$prefix" -DCMAKE_INSTALL_RPATH="$prefix/lib" \
  -DMALI_BRIDGE_PREFIX="$deps" -DCMAKE_SHARED_LINKER_FLAGS="-Wl,-rpath-link,$deps/lib" \
  -DBUILD_WSI_X11=ON -DBUILD_WSI_HEADLESS=OFF \
  -DBUILD_WSI_WAYLAND=OFF -DBUILD_WSI_DISPLAY=OFF -DSELECT_EXTERNAL_ALLOCATOR=none
cmake --build "$run/wsi-build" -j"$jobs"
DESTDIR="$stage" cmake --install "$run/wsi-build"
mkdir -p "$deps/android-override" "$deps/share/vulkan/icd.d"
install -m 644 "$work/sources/libc.so" "$deps/android-override/libc.so"
install -m 755 "$repo/scripts/gpu-run.sh" "$deps/bin/gpu-run"
python3 - "$deps" "$prefix" "$repo" <<'PY'
import json, sys
from pathlib import Path
deps, prefix, repo = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
icd={'file_format_version':'1.0.0','ICD':{'library_path':prefix+'/lib/libsysvk.so','api_version':'1.3.0'}}
(deps/'share/vulkan/icd.d/sysvk_icd.json').write_text(json.dumps(icd,indent=2)+'\n')
for path in (deps/'share/vulkan').rglob('*.json'): json.loads(path.read_text())
(deps/'sources.lock.json').write_bytes((repo/'sources.lock.json').read_bytes())
PY
readelf -dW "$deps/lib/libsysvk.so" | grep -E 'NEEDED|RUNPATH'
readelf -dW "$deps/lib/libhybris-common.so.1" | grep NODELETE
readelf -dW "$deps/lib/libhybris/linker/q.so" | grep NODELETE
printf '%s\n' "$stage" > "$work/last-stage.txt"
echo "BUILD_OK stage=$stage prefix=$prefix"
