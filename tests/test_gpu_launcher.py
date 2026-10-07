#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Desktop launcher tests: fake gpu-run and mocked dialogs only."""
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('gpu_launcher', ROOT / 'scripts/gpu-launcher.py')
LAUNCHER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LAUNCHER)


class DesktopLauncherTests(unittest.TestCase):
    def setUp(self):
        try:
            self.temporary = tempfile.TemporaryDirectory(prefix='pad-gpu-desktop-test.', dir='/opt')
        except PermissionError:
            self.skipTest('the supported chroot test environment needs write access to /opt')
        self.addCleanup(self.temporary.cleanup)
        self.prefix = Path(self.temporary.name)
        (self.prefix / 'bin').mkdir()
        self.launcher = self.prefix / 'bin/gpu-launcher.py'
        shutil.copy2(ROOT / 'scripts/gpu-launcher.py', self.launcher)
        self.runner = self.prefix / 'bin/gpu-run'
        self.runner.write_text('''#!/usr/bin/python3
import json, os, sys
print('STUB=' + json.dumps({'argv': sys.argv[1:], 'prefix': os.environ['PAD_GPU_PREFIX']}))
sys.exit(int(os.environ.get('STUB_EXIT', '0')))
''')
        self.runner.chmod(0o755)
        self.environment = dict(os.environ, XDG_STATE_HOME=str(self.prefix / 'state'))
        self.environment.pop('PAD_GPU_PREFIX', None)

    def run_launcher(self, *args, env=None):
        return subprocess.run(['/usr/bin/python3', str(self.launcher), *args],
                              env=dict(self.environment, **(env or {})), text=True,
                              capture_output=True, timeout=10)

    def logs(self):
        return sorted((self.prefix / 'state/pad-gpu/launches').glob('*.log'))

    def stub_data(self, log):
        return json.loads(next(line[5:] for line in log.read_text().splitlines() if line.startswith('STUB=')))

    def test_quoted_arguments_and_installed_prefix(self):
        command = 'my-app --title "hello world" "中文参数" --path="/tmp/a b"'
        result = self.run_launcher('--command', command)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.stub_data(self.logs()[0]),
                         {'argv': ['auto', *shlex.split(command)], 'prefix': str(self.prefix)})

    def test_software_is_explicit_and_arguments_are_not_interpreted_by_shell(self):
        marker = self.prefix / 'injected'
        command = 'app --title "$(touch ' + str(marker) + ')" ; touch ' + str(marker)
        result = self.run_launcher('--software', '--command', command)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.stub_data(self.logs()[0])['argv'], ['--software', 'auto', *shlex.split(command)])
        self.assertFalse(marker.exists())

    def test_each_launch_gets_a_private_log(self):
        for _ in range(2):
            result = self.run_launcher('--command', 'app')
            self.assertEqual(result.returncode, 0, result.stderr)
        logs = self.logs()
        self.assertEqual(len(logs), 2)
        self.assertEqual(stat.S_IMODE(logs[0].parent.stat().st_mode), 0o700)
        for log in logs:
            self.assertEqual(stat.S_IMODE(log.stat().st_mode), 0o600)

    def test_cancel_does_not_launch_or_create_log(self):
        cancelled = subprocess.CompletedProcess([], 1, '', '')
        with patch.object(LAUNCHER, 'zenity_path', return_value='/stub/zenity'), \
             patch.object(LAUNCHER.subprocess, 'run', return_value=cancelled), \
             patch.object(LAUNCHER.subprocess, 'Popen') as process, \
             patch.object(LAUNCHER, 'private_log') as log:
            self.assertEqual(LAUNCHER.main([]), 0)
            process.assert_not_called()
            log.assert_not_called()

    def test_invalid_quotes_do_not_start_program(self):
        result = self.run_launcher('--command', 'app "unterminated')
        self.assertEqual(result.returncode, 64)
        self.assertEqual(self.logs(), [])

    def test_missing_runner_and_invalid_prefix_are_reported_without_dialogs(self):
        self.runner.unlink()
        result = self.run_launcher('--command', 'app')
        self.assertEqual(result.returncode, 78)
        self.assertIn('gpu-run', result.stderr)
        for prefix in ('/opt/.', '/opt/..', '/tmp/bridge', '/opt/a/b'):
            with self.subTest(prefix=prefix):
                self.assertEqual(self.run_launcher('--command', 'app',
                    env={'PAD_GPU_PREFIX': prefix}).returncode, 64)

    def test_target_error_keeps_log_and_exit_status(self):
        result = self.run_launcher('--command', 'app', env={'STUB_EXIT': '23'})
        self.assertEqual(result.returncode, 23)
        self.assertIn('日志', result.stderr)
        self.assertIn('exit_status=23', self.logs()[0].read_text())


if __name__ == '__main__':
    unittest.main()
