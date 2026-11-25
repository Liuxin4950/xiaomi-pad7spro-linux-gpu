#!/usr/bin/env python3
"""Execute production wait predicates: cursor-only work must bypass the root frame gate."""
import argparse
import importlib.util
from pathlib import Path
import subprocess
import tempfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('source', type=Path)
a = p.parse_args()
here = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('copy_tests', here / 'run-x11-copy-regression.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
cpp = a.source / 'lorie/src/main/cpp/lorie'
s = (cpp / 'renderer.cpp').read_text().replace('bool Renderer::', 'Bool Renderer::')
names = (['Renderer::canUpdateCursorOverlayOnly'] if 'Renderer::canUpdateCursorOverlayOnly(' in s else []) + ['Renderer::shouldWait']
with tempfile.TemporaryDirectory(prefix='cursor-wake-') as tmp:
    out = Path(tmp)
    (out / 'production-wait.h').write_text('\n'.join(m.function(s, name) for name in names))
    binary = out / 'test'
    subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-fsanitize=undefined',
                    '-fno-sanitize-recover=all', '-I', str(out), '-I', str(cpp),
                    str(here / 'x11-cursor-wake-regression.cpp'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True, timeout=5)
