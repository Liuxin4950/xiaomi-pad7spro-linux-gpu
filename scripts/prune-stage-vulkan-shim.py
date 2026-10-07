#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Unlink only dynamic Vulkan shim entries inside a private build stage."""

import re
import stat
import sys
from pathlib import Path


def prune_shim(stage, prefix):
    stage = Path(stage)
    if not stage.is_absolute() or stage.is_symlink() or not stage.is_dir():
        raise ValueError('Stage must be an absolute, real directory')
    if not re.fullmatch(r'/opt/[a-zA-Z0-9_.-]+', prefix) or prefix.rsplit('/', 1)[-1] in {'.', '..'}:
        raise ValueError('Prefix must be a dedicated directory directly under /opt')
    lib = stage / prefix.lstrip('/') / 'lib'
    if lib.is_symlink() or not lib.resolve().is_relative_to(stage.resolve()):
        raise ValueError('Staged library directory escapes the private stage')
    if not lib.is_dir():
        raise ValueError('Staged library directory is missing')
    entries = [path for path in lib.iterdir()
               if re.fullmatch(r'libvulkan\.so(?:\.[0-9]+)*', path.name)]
    # Validate all matches first; never follow a library symlink or recurse.
    for path in entries:
        if not (stat.S_ISREG(path.lstat().st_mode) or path.is_symlink()):
            raise ValueError('Unexpected Vulkan shim entry type: ' + str(path))
    for path in entries:
        path.unlink()
    return len(entries)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit('usage: prune-stage-vulkan-shim.py STAGE /opt/PREFIX')
    try:
        count = prune_shim(sys.argv[1], sys.argv[2])
    except ValueError as error:
        sys.exit(str(error))
    print(f'libhybris: removed {count} staged Vulkan shim entries')
