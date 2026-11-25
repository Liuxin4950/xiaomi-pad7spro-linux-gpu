"""Exercise fresh-home migration and recovery; never call root, mount, ADB or a live desktop."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('configure', ROOT / 'scripts/configure-termux.py')
configure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(configure)


class TermuxConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / 'new-termux/home'
        self.home.mkdir(parents=True)
        self.prefix = self.root / 'new-termux/usr'
        (self.prefix / 'bin').mkdir(parents=True)
        for name in configure.REQUIRED:
            path = self.prefix / 'bin' / name
            path.write_text('#!/bin/sh\nexit 0\n')
            path.chmod(0o700)
        self.backup = self.root / 'backup'

    def plan(self):
        return configure.plan(self.home, self.prefix, '/data/custom/debian')

    def test_fresh_install_uses_new_home_prefix_and_rootfs_idempotently(self):
        report = self.plan()
        self.assertFalse((self.home / 'debian-shell.sh').exists())
        configure.apply(report, self.backup)
        config = (self.home / 'debian-gpu.conf').read_text()
        self.assertIn('/data/custom/debian', config)
        self.assertIn(str(self.prefix), config)
        self.assertIn(str(20000 + os.getuid() % 40000), config)
        self.assertEqual(self.plan()['entries'], [])
        for name in configure.ENTRIES:
            text = (self.home / name).read_text()
            self.assertTrue(text.startswith('#!' + str(self.prefix / 'bin/bash')))
            self.assertNotIn('/data/data/com.termux/files/home', text)
            subprocess.run(['bash', '-n', str(self.home / name)], check=True)
        # The Widget/ordinary paths actually forward arbitrary argv identically.
        (self.home / 'mali-work/desktop-zink.sh').write_text('printf "%s\\n" "$@"\n')
        for entry in ('debian-desktop.sh', '.shortcuts/debian-zink.sh'):
            result = subprocess.run(['bash', str(self.home / entry), 'two words', '$literal'],
                                    check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout.splitlines(), ['two words', '$literal'])

    def test_restore_original_content_mode_and_new_file_absence(self):
        old = self.home / 'debian-shell.sh'
        old.write_text('original user script\n')
        old.chmod(0o750)
        configure.apply(self.plan(), self.backup)
        receipt = json.loads((self.backup / 'receipt.json').read_text())
        configure.restore(self.backup, receipt, execute=True)
        self.assertEqual(old.read_text(), 'original user script\n')
        self.assertEqual(old.stat().st_mode & 0o777, 0o750)
        self.assertFalse((self.home / 'debian-gpu.conf').exists())

    def test_pinned_companion_verifies_and_restores_both_scopes(self):
        companion = self.root / 'companion'
        companion.mkdir()
        hashes = {}
        for name in ('loader.apk', 'termux-x11', 'termux-x11-preference'):
            data = b'fixture' if name == 'loader.apk' else b'#!/data/data/com.termux/files/usr/bin/bash\n'
            (companion / name).write_bytes(data)
            hashes[name] = configure.digest(data)
        (companion / 'SHA256.json').write_text(json.dumps(hashes))
        report = configure.plan(self.home, self.prefix, '/data/custom/debian', companion)
        configure.apply(report, self.backup)
        loader = self.prefix / 'libexec/termux-x11/loader.apk'
        self.assertEqual(loader.read_bytes(), b'fixture')
        self.assertEqual(loader.stat().st_mode & 0o777, 0o400)
        self.assertIn(str(self.prefix), (self.prefix / 'bin/termux-x11').read_text())
        configure.restore(self.backup, report, execute=True)
        self.assertFalse(loader.exists())
        self.assertEqual((self.prefix / 'bin/termux-x11').read_text(), '#!/bin/sh\nexit 0\n')
        (companion / 'loader.apk').write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            configure.plan(self.home, self.prefix, '/data/custom/debian', companion)

    def test_restore_refuses_user_edit_before_mutating_anything(self):
        report = self.plan()
        configure.apply(report, self.backup)
        (self.home / 'debian-root.sh').write_text('later edit')
        with self.assertRaisesRegex(ValueError, 'user changed'):
            configure.restore(self.backup, report, execute=True)
        self.assertTrue((self.home / 'debian-shell.sh').is_file())

    def test_corrupted_backup_refuses_restore(self):
        (self.home / 'debian-shell.sh').write_text('old')
        report = self.plan()
        configure.apply(report, self.backup)
        (self.backup / 'entry-0').write_text('corrupt')
        with self.assertRaisesRegex(ValueError, 'corrupted'):
            configure.restore(self.backup, report, execute=True)

    def test_partial_write_failure_restores_previous_entries(self):
        (self.home / 'debian-shell.sh').write_text('old')
        report = self.plan()
        real = configure.atomic
        failed = False

        def fault(path, *args, **kwargs):
            nonlocal failed
            if path == self.home / 'debian-root.sh' and not failed:
                failed = True
                raise OSError('injected write failure')
            return real(path, *args, **kwargs)

        with patch.object(configure, 'atomic', side_effect=fault):
            with self.assertRaisesRegex(OSError, 'injected'):
                configure.apply(report, self.backup)
        self.assertEqual((self.home / 'debian-shell.sh').read_text(), 'old')
        self.assertFalse((self.home / 'debian-desktop.sh').exists())

    def test_rejects_dependency_missing_path_injection_and_symlink_escape(self):
        (self.prefix / 'bin/adb').unlink()
        with self.assertRaisesRegex(ValueError, 'missing Termux'):
            configure.apply(self.plan(), self.backup)
        self.assertFalse(self.backup.exists())
        for value in ('/', '/data/a/../debian', '/data/a;id', '/data/two words'):
            with self.assertRaises(ValueError):
                configure.safe_path(value)
        (self.home / 'mali-work').symlink_to(self.root)
        with self.assertRaisesRegex(ValueError, 'escaping'):
            self.plan()


if __name__ == '__main__':
    unittest.main()
