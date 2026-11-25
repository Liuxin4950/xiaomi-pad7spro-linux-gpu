#!/usr/bin/env python3
"""Compile the actual patched X11 enqueue/ack functions against host buffer stubs."""
import argparse
from pathlib import Path
import re
import resource
import subprocess
import tempfile


def function(source, name):
    match = re.search(r'^(?:static\s+(?:inline\s+)?(?:__always_inline\s+)?)?(?:Bool|void)\s+'
                      + name + r'\([^;{]*\)\s*(?:const\s*)?\{', source, re.M)
    if not match:
        raise ValueError('production function not found: ' + name)
    start, body = match.start(), match.end() - 1
    depth = 1
    end = body + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end] + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='patched Termux:X11 source export')
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    cpp = args.source / 'lorie/src/main/cpp'
    header = (cpp / 'lorie/lorie.h').read_text()
    implementation = (cpp / 'lorie/InitOutput.c').read_text()
    start = header.index('typedef struct { int16_t x1')
    types = header[start:header.index('struct lorie_shared_server_state', start)]
    end = header.index('    } gpuCopyQueue;') + len('    } gpuCopyQueue;')
    start = header.rfind('    struct {', 0, end)
    queue = 'struct test_server_state { int lock, lockingPid; uint8_t waitForNextFrame;\n' + header[start:end] + '\n};\n'
    names = ['lorieTryScheduleGpuCopy', 'lorieGpuCopyIsDone', 'lorieGpuCopyFailed', 'lorieGpuCopyAck']
    scoped = 'static void lorieReleaseCpuMapping(' in implementation
    ordered = 'static Bool lorieLockGpuForCpuAccess(' in implementation
    deferred_wake = 'static void loriePerformFrameVblanks(' in implementation
    if scoped:
        names = ['lorieGpuCopyIsDone', 'lorieReleaseCpuMapping', 'lorieNeedsGpuLock',
                 *(['lorieLockGpuForCpuAccess'] if ordered else []),
                 'loriePrepareAccess', 'lorieFinishAccess', 'lorieTryScheduleGpuCopy',
                 'lorieGpuCopyFailed', 'lorieGpuCopyAck']
    if deferred_wake:
        names.append('loriePerformFrameVblanks')
    with tempfile.TemporaryDirectory(prefix='x11-copy-regression-') as directory:
        out = Path(directory)
        (out / 'production-types.h').write_text(('#define TEST_DEFERRED_COPY_WAKE 1\n' if deferred_wake else '')
                                               + ('#define TEST_QUEUED_CPU_GPU_ORDER 1\n' if ordered else '')
                                               + ('#define TEST_SCOPED_CPU_ACCESS 1\n' if scoped else '')
                                               + types + queue)
        (out / 'production-copy.h').write_text('\n'.join(function(implementation, name) for name in names))
        binary = out / 'regression'
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-fsanitize=undefined',
                        '-fno-sanitize-recover=all', '-I', str(out), '-I', str(cpp / 'lorie'),
                        str(Path(__file__).with_name('x11-copy-regression.c')), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True, timeout=10)
        # Exercise the complete production renderer method, including tick
        # interleavings and GL/fence ordering, rather than a duplicate model.
        renderer = (cpp / 'lorie/renderer.cpp').read_text()
        if 'lorieFrameGateBegin' in renderer:
            overlay = 'void Renderer::computePan(' in renderer
            (out / 'production-redraw.h').write_text(
                (function(renderer, 'Renderer::computePan') if overlay else '')
                + function(renderer, 'Renderer::redrawLocked'))
            binary = out / 'renderer-regression'
            subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=undefined', '-fno-sanitize-recover=all',
                            *(['-DTEST_CURSOR_OVERLAY=1'] if overlay else []),
                            '-I', str(out), '-I', str(cpp / 'lorie'),
                            str(Path(__file__).with_name('x11-renderer-regression.cpp')),
                            '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True, timeout=10)


if __name__ == '__main__':
    main()
