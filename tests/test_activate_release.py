#!/usr/bin/env python3
"""Exercise migration failures in a private filesystem, never real system links."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('activate_release', ROOT / 'scripts/activate-release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.links = self.root / 'bin'
        self.links.mkdir()
        for name in ('gpu-run', 'gpu-launcher'):
            (self.links / name).symlink_to('/old/' + name)
        self.entry = self.root / 'entry.desktop'
        self.entry.write_text('old-content')
        self.entry.chmod(0o751)
        os.setxattr(self.entry, 'user.gpu-test', b'original')
        self.backup = self.root / 'backup'
        self.plan = dict(applied=False, entries=[dict(path=str(self.entry),
            before_sha256=release.digest(self.entry), after_sha256=hashlib.sha256(b'new-content').hexdigest())])
        self.link_patch = patch.object(release, 'LINK_DIR', self.links)
        self.link_patch.start()
        self.addCleanup(self.link_patch.stop)
        self.plan_patch = patch.object(release.subprocess, 'check_output', return_value=json.dumps(self.plan))
        self.plan_patch.start()
        self.addCleanup(self.plan_patch.stop)

    def assert_original(self):
        for name in ('gpu-run', 'gpu-launcher'):
            self.assertEqual(str((self.links / name).readlink()), '/old/' + name)
        self.assertEqual(self.entry.read_text(), 'old-content')
        self.assertEqual(self.entry.stat().st_mode & 0o777, 0o751)
        self.assertEqual(os.getxattr(self.entry, 'user.gpu-test'), b'original')

    def migrate(self, *args, **kwargs):
        self.assertIn('--expected-plan', args[0])
        self.entry.write_text('new-content')
        return subprocess.CompletedProcess(args[0], 0)

    def test_success_manual_restore_and_idempotence_preserve_metadata(self):
        with patch.object(release.subprocess, 'run', side_effect=self.migrate):
            report = release.activate(Path('/new'), self.backup)
        self.assertEqual(report['state'], 'activated')
        self.assertEqual(self.entry.read_text(), 'new-content')
        release.restore(self.backup, report, apply=True)
        release.restore(self.backup, report, apply=True)
        self.assert_original()
        self.assertEqual(json.loads((self.backup / 'restore-plan.json').read_text())['state'], 'rolled-back')
        self.assertEqual(self.backup.stat().st_mode & 0o777, 0o700)

    def test_second_link_failure_restores_first_without_running_migration(self):
        original = release.replace_link
        count = 0
        def fail_once(path, target):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError('simulated link failure')
            original(path, target)
        with patch.object(release, 'replace_link', side_effect=fail_once), \
                patch.object(release.subprocess, 'run') as migration:
            with self.assertRaisesRegex(RuntimeError, 'restored original'):
                release.activate(Path('/new'), self.backup)
            migration.assert_not_called()
        self.assert_original()

    def test_partial_desktop_failure_restores_bytes_mode_and_xattrs(self):
        def fail(*args, **kwargs):
            self.migrate(*args, **kwargs)
            self.entry.chmod(0o600)
            os.setxattr(self.entry, 'user.gpu-test', b'changed')
            raise subprocess.CalledProcessError(1, args[0])
        with patch.object(release.subprocess, 'run', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'restored original'):
                release.activate(Path('/new'), self.backup)
        self.assert_original()

    def test_post_deployment_user_edit_prevents_any_restore_mutation(self):
        with patch.object(release.subprocess, 'run', side_effect=self.migrate):
            report = release.activate(Path('/new'), self.backup)
        self.entry.write_text('user-edit')
        with self.assertRaisesRegex(ValueError, 'outside this transaction'):
            release.restore(self.backup, report, apply=True)
        self.assertEqual(self.entry.read_text(), 'user-edit')
        self.assertEqual(str((self.links / 'gpu-run').readlink()), '/new/bin/gpu-run')

    def test_partial_termux_helper_update_restores_all_planned_files(self):
        # A desktop migration now includes shared shell/stop helpers. A failure
        # after changing just one must restore both, including original modes.
        helpers = []
        for name in ('debian-shell.sh', 'debian-stop.sh'):
            path = self.root / name
            path.write_text('original-' + name)
            path.chmod(0o700)
            helpers.append(path)
            self.plan['entries'].append(dict(path=str(path), before_sha256=release.digest(path),
                after_sha256=hashlib.sha256(b'updated-helper').hexdigest()))
        def fail_after_first_helper(*args, **kwargs):
            self.migrate(*args, **kwargs)
            helpers[0].write_text('updated-helper')
            helpers[0].chmod(0o600)
            raise subprocess.CalledProcessError(1, args[0])
        with patch.object(release.subprocess, 'check_output', return_value=json.dumps(self.plan)), \
                patch.object(release.subprocess, 'run', side_effect=fail_after_first_helper):
            with self.assertRaisesRegex(RuntimeError, 'restored original'):
                release.activate(Path('/new'), self.backup)
        self.assert_original()
        for path in helpers:
            self.assertEqual(path.read_text(), 'original-' + path.name)
            self.assertEqual(path.stat().st_mode & 0o777, 0o700)

    def test_corrupt_backup_prevents_restore(self):
        with patch.object(release.subprocess, 'run', side_effect=self.migrate):
            report = release.activate(Path('/new'), self.backup)
        (self.backup / 'entry-0').write_text('corrupt')
        with self.assertRaisesRegex(ValueError, 'corrupted'):
            release.restore(self.backup, report, apply=True)
        self.assertEqual(self.entry.read_text(), 'new-content')


if __name__ == '__main__':
    unittest.main()
