#!/usr/bin/env python3
"""Exercise candidate cursor geometry and transaction snapshots without Android."""
import argparse
import importlib.util
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location('copy_tests', here / 'run-x11-copy-regression.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = (args.source / 'lorie/src/main/cpp/lorie/renderer.cpp').read_text()
    names = ['computeCursorOverlayScale', 'computeCursorOverlayRect', 'applyCursorOverlayIfDirty', 'resendCursorOverlayBuffer', 'teardownCursorOverlay']
    with tempfile.TemporaryDirectory(prefix='x11-cursor-regression-') as directory:
        out = Path(directory)
        (out / 'production-cursor.h').write_text('\n'.join(
            module.function(source.replace('bool Renderer::computeCursorOverlayRect(',
                                           'Bool Renderer::computeCursorOverlayRect('), 'Renderer::' + name)
            for name in names).replace('__builtin_available(android 29, *)', 'true'))
        binary = out / 'regression'
        subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-pthread',
                        '-fsanitize=undefined', '-fno-sanitize-recover=all', '-I', str(out),
                        str(here / 'x11-cursor-regression.cpp'), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True, timeout=10)


if __name__ == '__main__':
    main()
