#!/usr/bin/env python3
"""Exercise the shared hardware environment and run-gpu alias without devices."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class GlobalEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pad-gpu-global-test.', dir='/opt')
        self.addCleanup(self.temp.cleanup)
        self.prefix = Path(self.temp.name)
        (self.prefix / 'bin').mkdir()
        self.env_script = self.prefix / 'bin/gpu-env'
        self.run_script = self.prefix / 'bin/run-gpu'
        shutil.copy2(ROOT / 'scripts/gpu-env.sh', self.env_script)
        shutil.copy2(ROOT / 'scripts/run-gpu.sh', self.run_script)
        self.env_script.chmod(0o755)
        self.run_script.chmod(0o755)
        self.stub_log = self.prefix / 'argv.json'
        stub = self.prefix / 'bin/gpu-run'
        stub.write_text('''#!/usr/bin/python3
import json, os, sys
open(os.environ['GPU_STUB_LOG'], 'w').write(json.dumps(sys.argv[1:]))
''')
        stub.chmod(0o755)

    def run_env(self, *args, **overrides):
        env = dict(os.environ, PAD_GPU_PREFIX=str(self.prefix), GPU_STUB_LOG=str(self.stub_log), **overrides)
        return subprocess.run(args, env=env, text=True, capture_output=True, timeout=10)

    def test_sourced_environment_replaces_stale_renderer_without_preload(self):
        command = 'set -u; before=$(set +o); source "$1"; after=$(set +o); [[ "$before" == "$after" ]] || exit 71; env -0'
        result = self.run_env('/bin/bash', '-c', command, 'test', str(self.env_script),
                              LIBGL_ALWAYS_SOFTWARE='1', GALLIUM_DRIVER='llvmpipe',
                              VK_DRIVER_FILES='/wrong/icd.json', LD_PRELOAD='/wrong/preload.so',
                              SENTINEL_APP_SETTING='keep')
        self.assertEqual(result.returncode, 0, result.stderr)
        values = dict(item.split(b'=', 1) for item in result.stdout.encode().split(b'\0') if item)
        self.assertEqual(values[b'PAD_GPU_PREFIX'], str(self.prefix).encode())
        self.assertEqual(values[b'VK_DRIVER_FILES'], str(self.prefix / 'share/vulkan/icd.d/sysvk_icd.json').encode())
        self.assertEqual(values[b'GALLIUM_DRIVER'], b'zink')
        self.assertEqual(values[b'MESA_LOADER_DRIVER_OVERRIDE'], b'zink')
        self.assertNotIn(b'LIBGL_ALWAYS_SOFTWARE', values)
        self.assertNotIn(b'LD_PRELOAD', values)
        self.assertEqual(values[b'SENTINEL_APP_SETTING'], b'keep')

    def test_source_is_safe_under_nounset_and_keeps_session_options(self):
        command = 'set -euo pipefail; before=$(set +o); source "$1"; after=$(set +o); [[ "$before" == "$after" ]]; printf "%s\\n" "$VK_DRIVER_FILES"'
        result = self.run_env('/bin/bash', '-c', command, 'test', str(self.env_script))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(self.prefix / 'share/vulkan/icd.d/sysvk_icd.json'))

    def test_run_gpu_defaults_to_auto_and_preserves_arguments(self):
        result = self.run_env(str(self.run_script), 'my-electron-app', '--profile', 'a b')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.stub_log.read_text()), ['auto', 'my-electron-app', '--profile', 'a b'])

    def test_run_gpu_keeps_explicit_modes_and_software_opt_in(self):
        cases = [(['vulkan', '/tmp/client', '--size', '10 20'], ['vulkan', '/tmp/client', '--size', '10 20']),
                 (['--software', 'chromium'], ['--software', 'chromium'])]
        for arguments, expected in cases:
            with self.subTest(arguments=arguments):
                self.stub_log.unlink(missing_ok=True)
                result = self.run_env(str(self.run_script), *arguments)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(self.stub_log.read_text()), expected)

    def test_profile_hook_is_valid_posix_and_only_sources_under_bash(self):
        content = '''# Managed by pad-gpu; source the active bridge environment for Bash sessions.
if [ -n "${BASH_VERSION-}" ] && [ -r /usr/local/bin/gpu-env ]; then
  . /usr/local/bin/gpu-env
fi
'''
        parsed = subprocess.run(['/bin/dash', '-n'], input=content, text=True, capture_output=True)
        self.assertEqual(parsed.returncode, 0, parsed.stderr)
        self.assertIn('[ -n "${BASH_VERSION-}" ]', content)
        self.assertIn('/usr/local/bin/gpu-env', content)


if __name__ == '__main__':
    unittest.main()
