#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Reject hooks that send glibc allocations to the unhooked Bionic allocator."""

import re
import sys
from pathlib import Path


ALLOCATOR_SYMBOLS = {
    'malloc', 'calloc', 'realloc', 'reallocarray', 'free', 'cfree',
    'memalign', 'posix_memalign', 'aligned_alloc', 'valloc', 'pvalloc',
    'malloc_usable_size', 'strdup', 'strndup', 'wcsdup',
    'asprintf', 'vasprintf', 'getdelim', 'getline',
    'scandir', 'scandir64', 'scandirat', 'scandirat64',
    'open_memstream', 'open_wmemstream',
    'getcwd', 'get_current_dir_name', 'realpath', 'canonicalize_file_name', 'tempnam',
    'scanf', 'sscanf', 'fscanf', 'vscanf', 'vsscanf', 'vfscanf',
}
ALLOCATOR_SYMBOLS |= {'__' + symbol for symbol in ALLOCATOR_SYMBOLS}
ALLOCATOR_SYMBOLS |= {'__libc_' + symbol for symbol in (
    'malloc', 'calloc', 'realloc', 'free', 'memalign', 'valloc', 'pvalloc')}
ALLOCATOR_SYMBOLS |= {'__asprintf_chk', '__vasprintf_chk'}
ALLOCATOR_SYMBOLS |= {'__' + version + '_' + symbol for version in ('isoc99', 'isoc23')
                      for symbol in ('scanf', 'sscanf', 'fscanf', 'vscanf', 'vsscanf', 'vfscanf')}

# These wrappers fail without touching FILE or allocating a caller-owned buffer.
# Unhooking them would let Bionic inspect a glibc FILE, which is also unsafe.
SAFE_STUBS = {
    'getdelim': '_hybris_bridge_unsupported_getdelim',
    'getline': '_hybris_bridge_unsupported_getline',
    'open_memstream': '_hybris_bridge_unsupported_open_memstream',
    'open_wmemstream': '_hybris_bridge_unsupported_open_wmemstream',
}
SAFE_SCANF_HOOKS = {
    name: '_hybris_bridge_' + name for name in ('scanf', 'sscanf', 'vscanf', 'vsscanf')
}
SAFE_SCANF_HOOKS.update({name: '_hybris_hook_' + name for name in ('fscanf', 'vfscanf')})
SAFE_HOOKS = SAFE_STUBS | SAFE_SCANF_HOOKS
REQUIRED_TABLES = {'hooks_properties', 'hooks_common', 'hooks_mm', 'hooks_n', 'hooks_p'}
REQUIRED_OWNERSHIP_PAIRS = (
    ('fopen', 'fclose'), ('fdopen', 'fclose'), ('fmemopen', 'fclose'),
    ('popen', 'pclose'), ('opendir', 'closedir'), ('fdopendir', 'closedir'),
    ('getaddrinfo', 'freeaddrinfo'), ('newlocale', 'freelocale'),
    ('duplocale', 'freelocale'),
)


def without_comments(source):
    """Preserve strings and line numbers while removing C comments."""
    return re.sub(
        r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*.*?\*/|//[^\n]*',
        lambda match: re.sub(r'[^\n]', ' ', match[0])
        if match[0].startswith(('/*', '//')) else match[0], source, flags=re.S)


def allocator_target(name):
    return name in ALLOCATOR_SYMBOLS or (
        name.startswith('_hybris_hook_')
        and name.removeprefix('_hybris_hook_') in ALLOCATOR_SYMBOLS)


def check_hooks(source):
    source = without_comments(source)
    tables = list(re.finditer(
        r'\bstatic\s+struct\s+_hook\s+(\w+)\s*\[\s*\]\s*=\s*\{(.*?)\n\s*\};',
        source, re.S))
    missing = REQUIRED_TABLES - {table[1] for table in tables}
    if missing:
        raise ValueError('Missing hook tables: ' + ', '.join(sorted(missing)))
    present = set()
    for table in tables:
        body = table[2]
        for entry in re.finditer(r'\b(HOOK_\w+)\s*\(([^()]*)\)', body):
            macro, arguments = entry[1], [part.strip() for part in entry[2].split(',')]
            if macro not in {'HOOK_DIRECT', 'HOOK_DIRECT_NO_DEBUG', 'HOOK_INDIRECT', 'HOOK_TO'}:
                raise ValueError('Unknown hook macro in ' + table[1] + ': ' + macro)
            if len(arguments) != (2 if macro == 'HOOK_TO' else 1):
                raise ValueError('Unrecognized hook entry in ' + table[1] + ': ' + entry[0])
            symbol = arguments[0]
            present.add(symbol)
            target = arguments[-1] if macro == 'HOOK_TO' else (
                '_hybris_hook_' + symbol if macro == 'HOOK_INDIRECT' else symbol)
            safe_hook = macro in {'HOOK_TO', 'HOOK_INDIRECT'} and SAFE_HOOKS.get(symbol) == target
            if not safe_hook and any(allocator_target(name) for name in arguments):
                raise ValueError('Cross-allocator hook in ' + table[1] + ': ' + entry[0])
        # Upstream also supports literal entries such as {"sigsetjmp", __sigsetjmp}.
        for entry in re.finditer(r'\{\s*"([^"\\]+)"\s*,\s*([^{}]+)\}', body):
            names = [entry[1]] + re.findall(r'\b\w+\b', entry[2])
            present.add(entry[1])
            if any(allocator_target(name) for name in names):
                raise ValueError('Cross-allocator literal hook in ' + table[1] + ': ' + entry[0])
    for pair in REQUIRED_OWNERSHIP_PAIRS:
        if not set(pair) <= present:
            raise ValueError('Required ownership hook pair missing: ' + '/'.join(pair))
    for symbol, target in SAFE_HOOKS.items():
        explicit = r'HOOK_TO\s*\(\s*' + symbol + r'\s*,\s*' + target + r'\s*\)'
        indirect = r'HOOK_INDIRECT\s*\(\s*' + symbol + r'\s*\)' if target == '_hybris_hook_' + symbol else r'(?!)'
        if not re.search(explicit + '|' + indirect, source):
            raise ValueError('Required safe allocation hook missing: ' + symbol)
    return len(tables)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit('usage: check-libhybris-hooks.py SOURCE/hybris/common/hooks.c')
    try:
        count = check_hooks(Path(sys.argv[1]).read_text())
    except ValueError as error:
        sys.exit(str(error))
    print(f'libhybris: allocator isolation verified across {count} hook tables')
