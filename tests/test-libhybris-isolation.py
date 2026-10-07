#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise allocator boundaries in the actual locked and patched source."""

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def load_helper(filename):
    spec = importlib.util.spec_from_file_location(filename, REPO / 'scripts' / (filename + '.py'))
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    return helper


CHECK = load_helper('check-libhybris-hooks')
PRUNE = load_helper('prune-stage-vulkan-shim')


def function_source(source, name):
    start = source.index(name + '(')
    start = source.rfind('\n', 0, start) + 1
    opening = source.index('{', start)
    depth = 1
    closing = opening + 1
    while depth:
        if source[closing] == '{':
            depth += 1
        elif source[closing] == '}':
            depth -= 1
        closing += 1
    return source[start:closing]


class HookIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix='gpu-hook-tests-')
        cls.source_dir = Path(cls.directory.name)
        item = next(item for item in json.loads((REPO / 'sources.lock.json').read_text())['git_sources']
                    if item['name'] == 'libhybris')
        archive = subprocess.Popen(['git', '-C', str(REPO / 'build/sources/libhybris'),
                                    'archive', item['commit']], stdout=subprocess.PIPE)
        extracted = subprocess.run(['tar', '-xf', '-', '-C', str(cls.source_dir)], stdin=archive.stdout)
        archive.stdout.close()
        if extracted.returncode or archive.wait():
            raise RuntimeError('Cannot export locked libhybris source')
        subprocess.run(['git', 'init', '--quiet', str(cls.source_dir)], check=True)
        for patch in item['patches']:
            subprocess.run(['git', '-C', str(cls.source_dir), 'apply', '--check',
                            str(REPO / patch['path'])], check=True)
            subprocess.run(['git', '-C', str(cls.source_dir), 'apply',
                            str(REPO / patch['path'])], check=True)
        cls.source = (cls.source_dir / 'hybris/common/hooks.c').read_text()

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def inject(self, table, entry):
        marker = 'static struct _hook ' + table + '[] = {'
        return self.source.replace(marker, marker + '\n    ' + entry, 1)

    def test_real_patch_preserves_handle_pairs_and_has_no_allocator_hooks(self):
        self.assertEqual(CHECK.check_hooks(self.source), 5)

    def test_every_table_rejects_allocators_and_directory_aliases(self):
        for table in sorted(CHECK.REQUIRED_TABLES):
            for symbol in ('malloc', 'scandir64', 'scandirat', 'scandirat64', '__strdup'):
                with self.subTest(table=table, symbol=symbol):
                    with self.assertRaises(ValueError):
                        CHECK.check_hooks(self.inject(table, 'HOOK_DIRECT_NO_DEBUG(' + symbol + '),'))

    def test_macro_and_literal_alias_targets_are_checked(self):
        for table in sorted(CHECK.REQUIRED_TABLES):
            for entry in ('HOOK_TO(innocent_alias, _hybris_hook_scandirat),',
                          'HOOK_TO(innocent_alias, strdup),',
                          '{"innocent_alias", realloc, realloc},',
                          '{"scandir64", innocent, innocent},'):
                with self.subTest(table=table, entry=entry):
                    with self.assertRaises(ValueError):
                        CHECK.check_hooks(self.inject(table, entry))

    def test_new_hook_tables_are_also_checked(self):
        source = self.source + '\nstatic struct _hook hooks_future[] = {\nHOOK_TO(scandirat64, _hybris_hook_scandirat),\n};\n'
        with self.assertRaises(ValueError):
            CHECK.check_hooks(source)

    def test_optional_allocators_and_scanf_abi_aliases_are_rejected(self):
        for symbol in ('getcwd', 'realpath', 'tempnam', '__isoc99_sscanf', '__isoc23_vfscanf'):
            with self.subTest(symbol=symbol), self.assertRaises(ValueError):
                CHECK.check_hooks(self.inject('hooks_p', 'HOOK_DIRECT_NO_DEBUG(' + symbol + '),'))

    def test_comments_do_not_create_false_allocator_hooks(self):
        source = self.inject('hooks_p', '// HOOK_DIRECT(malloc),\n/* HOOK_TO(scandir64, malloc) */')
        self.assertEqual(CHECK.check_hooks(source), 5)

    def test_safe_stubs_cannot_be_replaced_by_glibc_forwarders(self):
        for symbol, target in CHECK.SAFE_HOOKS.items():
            original = ('HOOK_INDIRECT(' + symbol + ')' if target == '_hybris_hook_' + symbol
                        else 'HOOK_TO(' + symbol + ', ' + target + ')')
            for replacement in ('HOOK_DIRECT_NO_DEBUG(' + symbol + ')',
                                'HOOK_TO(' + symbol + ', ' + symbol + ')'):
                with self.subTest(symbol=symbol, replacement=replacement):
                    self.assertIn(original, self.source)
                    with self.assertRaises(ValueError):
                        CHECK.check_hooks(self.source.replace(original, replacement))

    def test_real_stdio_guards_preserve_normal_io_and_reject_allocation(self):
        names = ['_hybris_bridge_scanf_allocates', '_hybris_bridge_vsscanf',
                 '_hybris_bridge_vscanf', '_hybris_bridge_sscanf', '_hybris_bridge_scanf',
                 '_hybris_hook_fscanf', '_hybris_hook_vfscanf'] + list(CHECK.SAFE_STUBS.values())
        harness = '''
#define _GNU_SOURCE
#define FP_ATTRIB
#define TRACE_HOOK(...)
#include <stdio.h>
#include <stdint.h>
#include <stdarg.h>
#include <string.h>
#include <wchar.h>
#include <errno.h>
#include <assert.h>
static FILE *_get_actual_fp(FILE *fp) { return fp; }
'''
        harness += '\n\n'.join(function_source(self.source, name) for name in names)
        harness += r'''
static int call_vfscanf(FILE *fp, const char *fmt, ...) {
    va_list args; va_start(args, fmt);
    int result = _hybris_hook_vfscanf(fp, fmt, args);
    va_end(args); return result;
}
static int call_vsscanf(const char *input, const char *fmt, ...) {
    va_list args; va_start(args, fmt);
    int result = _hybris_bridge_vsscanf(input, fmt, args);
    va_end(args); return result;
}
static int call_vscanf(const char *fmt, ...) {
    va_list args; va_start(args, fmt);
    int result = _hybris_bridge_vscanf(fmt, args);
    va_end(args); return result;
}
int main(void) {
    char *buffer = (char *)(uintptr_t)0x1234;
    wchar_t *wide = (wchar_t *)(uintptr_t)0x5678;
    size_t capacity = 77;
    FILE *invalid = (FILE *)(uintptr_t)1;
    errno = 0;
    assert(_hybris_bridge_unsupported_getdelim(&buffer, &capacity, '\n', invalid) == -1);
    assert(errno == ENOSYS && buffer == (char *)(uintptr_t)0x1234 && capacity == 77);
    errno = 0;
    assert(_hybris_bridge_unsupported_getline(&buffer, &capacity, invalid) == -1);
    assert(errno == ENOSYS && buffer == (char *)(uintptr_t)0x1234 && capacity == 77);
    errno = 0;
    assert(_hybris_bridge_unsupported_open_memstream(&buffer, &capacity) == NULL);
    assert(errno == ENOSYS && buffer == (char *)(uintptr_t)0x1234 && capacity == 77);
    errno = 0;
    assert(_hybris_bridge_unsupported_open_wmemstream(&wide, &capacity) == NULL);
    assert(errno == ENOSYS && wide == (wchar_t *)(uintptr_t)0x5678 && capacity == 77);
    const char *ordinary[] = {"%d %s", "%[a%m]", "%[]m]", "%%m %ls %Lf %zu", "%2$10s", "%*s"};
    const char *allocating[] = {"%ms", "%mc", "%m[a-z]", "%2$16ms", "%*ms", "%mls"};
    for (size_t i=0; i<sizeof(ordinary)/sizeof(*ordinary); ++i)
        assert(!_hybris_bridge_scanf_allocates(ordinary[i]));
    for (size_t i=0; i<sizeof(allocating)/sizeof(*allocating); ++i) {
        assert(_hybris_bridge_scanf_allocates(allocating[i]));
        errno = 0;
        assert(_hybris_bridge_sscanf("anything", allocating[i], &buffer) == EOF);
        assert(errno == ENOSYS && buffer == (char *)(uintptr_t)0x1234);
    }
    errno = 0;
    assert(call_vsscanf("anything", "%ms", &buffer) == EOF && errno == ENOSYS);
    errno = 0;
    assert(_hybris_bridge_scanf("%ms", &buffer) == EOF && errno == ENOSYS);
    errno = 0;
    assert(call_vscanf("%ms", &buffer) == EOF && errno == ENOSYS);
    errno = 0;
    assert(_hybris_hook_fscanf(invalid, "%ms", &buffer) == EOF && errno == ENOSYS);
    errno = 0;
    assert(call_vfscanf(invalid, "%ms", &buffer) == EOF && errno == ENOSYS);
    int number = 0; char word[16] = {0};
    assert(_hybris_bridge_sscanf("42 hello", "%d %15s", &number, word) == 2);
    assert(number == 42 && strcmp(word, "hello") == 0);
    assert(call_vsscanf("23", "%d", &number) == 1 && number == 23);
    FILE *fp = tmpfile(); assert(fp); fputs("17 19", fp); rewind(fp);
    assert(_hybris_hook_fscanf(fp, "%d", &number) == 1 && number == 17);
    assert(call_vfscanf(fp, "%d", &number) == 1 && number == 19);
    fclose(fp);
    assert(ungetc('7', stdin) != EOF);
    assert(_hybris_bridge_scanf("%d", &number) == 1 && number == 7);
    assert(ungetc('8', stdin) != EOF);
    assert(call_vscanf("%d", &number) == 1 && number == 8);
    return 0;
}
'''
        path = self.source_dir / 'stdio-guard-test.c'
        path.write_text(harness)
        binary = self.source_dir / 'stdio-guard-test'
        subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror', str(path), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], stdin=subprocess.DEVNULL, check=True)


class StageUnlinkTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='gpu-stage-tests-')
        self.root = Path(self.directory.name)
        self.stage = self.root / 'stage'
        self.lib = self.stage / 'opt/candidate/lib'
        self.lib.mkdir(parents=True)

    def tearDown(self):
        self.directory.cleanup()

    def test_only_precise_shim_names_are_unlinked(self):
        target = self.root / 'system-vulkan'; target.write_text('system loader')
        (self.lib / 'libvulkan.so').symlink_to(target)
        (self.lib / 'libvulkan.so.1.2.183').write_text('shim')
        (self.lib / 'libvulkan.so.backup').write_text('backup')
        (self.lib / 'libsysvk.so').write_text('bridge')
        self.assertEqual(PRUNE.prune_shim(self.stage, '/opt/candidate'), 2)
        self.assertEqual(target.read_text(), 'system loader')
        self.assertEqual((self.lib / 'libvulkan.so.backup').read_text(), 'backup')
        self.assertTrue((self.lib / 'libsysvk.so').exists())

    def test_symlinked_library_directory_is_rejected(self):
        self.lib.rmdir()
        target = self.root / 'outside'; target.mkdir()
        (target / 'libvulkan.so').write_text('system loader')
        self.lib.symlink_to(target)
        with self.assertRaises(ValueError):
            PRUNE.prune_shim(self.stage, '/opt/candidate')
        self.assertEqual((target / 'libvulkan.so').read_text(), 'system loader')

    def test_unexpected_directory_fails_before_any_unlink(self):
        (self.lib / 'libvulkan.so').write_text('shim')
        (self.lib / 'libvulkan.so.1').mkdir()
        with self.assertRaises(ValueError):
            PRUNE.prune_shim(self.stage, '/opt/candidate')
        self.assertTrue((self.lib / 'libvulkan.so').is_file())

    def test_dot_prefixes_are_rejected(self):
        for prefix in ('/opt/.', '/opt/..'):
            with self.subTest(prefix=prefix), self.assertRaises(ValueError):
                PRUNE.prune_shim(self.stage, prefix)


if __name__ == '__main__':
    unittest.main()
