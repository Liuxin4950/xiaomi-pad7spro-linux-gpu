#!/usr/bin/env python3
"""Pinned exports must ignore dirty sources and old local object directories."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_x11', ROOT / 'scripts/build-x11.py')
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class X11BuildTests(unittest.TestCase):
    def test_export_uses_commit_and_ignores_old_objects(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / 'cache'
            subprocess.run(['git', 'init', '-q', str(cache)], check=True)
            (cache / 'source.c').write_text('committed')
            subprocess.run(['git', '-C', str(cache), 'add', 'source.c'], check=True)
            subprocess.run(['git', '-C', str(cache), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                            'commit', '-qm', 'fixture'], check=True)
            commit = build.text(['git', '-C', cache, 'rev-parse', 'HEAD'])
            (cache / 'source.c').write_text('dirty')
            (cache / '.cxx').mkdir()
            (cache / '.cxx/old.o').write_text('old object')
            revisions = {}
            destination = root / 'output'
            build.export_tree(cache, commit, destination, revisions)
            self.assertEqual((destination / 'source.c').read_text(), 'committed')
            self.assertFalse((destination / '.cxx').exists())
            self.assertFalse((destination / '.git').exists())
            self.assertEqual((cache / 'source.c').read_text(), 'dirty')
            self.assertEqual(revisions, {'.': commit})

    def test_pinned_configuration_drift_is_rejected_without_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'build.gradle'
            path.write_text('changed upstream')
            with self.assertRaises(ValueError):
                build.replace_once(path, 'expected', 'new')
            self.assertEqual(path.read_text(), 'changed upstream')

    def test_native_source_hash_detects_header_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'shared.h').write_text('old layout')
            before = build.tree_hashes(root)
            (root / 'shared.h').write_text('new layout')
            self.assertNotEqual(before, build.tree_hashes(root))


if __name__ == '__main__':
    unittest.main()
