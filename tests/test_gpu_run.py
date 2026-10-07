#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Launcher contract tests. Stub programs only: no GPU, X11 or Android operations."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
STUB = '''#!/usr/bin/python3
import json, os, sys
keys = ('VK_DRIVER_FILES', 'VK_IMPLICIT_LAYER_PATH', 'VK_INSTANCE_LAYERS',
        'VK_ADD_DRIVER_FILES', 'HYBRIS_LD_LIBRARY_PATH', 'HYBRIS_LINKER_DIR',
        'HYBRIS_VULKANPLATFORM', 'LD_LIBRARY_PATH', 'MESA_LOADER_DRIVER_OVERRIDE',
        'GALLIUM_DRIVER', 'LIBGL_ALWAYS_SOFTWARE', 'DISABLE_WSI_LAYER', 'vblank_mode',
        'DISPLAY', 'SENTINEL_APP_SETTING')
print(json.dumps({'argv': sys.argv[1:], 'env': {key: os.environ.get(key) for key in keys}}))
sys.exit(int(os.environ.get('TEST_EXIT', '0')))
'''
HARNESS = '''
source "$1"
shift
# Test-only overrides after sourcing; production has no bypass environment switch.
check_android() {
  printf 'android:%s\\n' "$1" >> "$TEST_CHECKS"
  [[ ${MOCK_ANDROID_FAIL:-0} != 1 ]] || return 78
}
check_x11() {
  printf 'x11\\n' >> "$TEST_CHECKS"
  [[ ${MOCK_X11_FAIL:-0} != 1 ]] || return 78
}
if [[ -n ${MOCK_ALIAS_BINARY:-} ]]; then
  resolve_binary() { binary=$MOCK_ALIAS_BINARY; }
fi
if [[ ${MOCK_READELF:-0} == 1 ]]; then
  readelf() { printf '  (RUNPATH) [%s/lib]\\n' "$prefix"; }
fi
main "$@"
'''


class LauncherTests(unittest.TestCase):
    def setUp(self):
        try:
            self.temporary = tempfile.TemporaryDirectory(prefix='pad-gpu-launcher-test.', dir='/opt')
        except PermissionError:
            self.skipTest('the supported chroot test environment needs write access to /opt')
        self.addCleanup(self.temporary.cleanup)
        self.prefix = Path(self.temporary.name)
        self.make_install(self.prefix)
        self.launcher = self.prefix / 'bin/gpu-run'
        self.checks = self.prefix / 'checks'

    def make_install(self, prefix):
        for name in ('lib/libsysvk.so', 'lib/libhardware.so.2', 'lib/libhybris-common.so.1',
                     'lib/libhybris/linker/q.so', 'lib/libahb-wrapper.so.1', 'android-override/libc.so',
                     'share/vulkan/implicit_layer.d/libVkLayer_window_system_integration.so'):
            path = prefix / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('test fixture, never loaded\n')
        icd = prefix / 'share/vulkan/icd.d/sysvk_icd.json'
        icd.parent.mkdir(parents=True, exist_ok=True)
        icd.write_text(json.dumps({'ICD': {'library_path': str(prefix / 'lib/libsysvk.so')}}))
        (prefix / 'share/vulkan/implicit_layer.d/VkLayer_window_system_integration.json').write_text(
            json.dumps({'layer': {'name': 'VK_LAYER_window_system_integration',
                                 'library_path': './libVkLayer_window_system_integration.so'}}))
        (prefix / 'bin').mkdir(exist_ok=True)
        shutil.copy2(ROOT / 'scripts/gpu-run.sh', prefix / 'bin/gpu-run')
        for name in ('app', 'chromium', 'electron42', 'electron42-unknown', 'fake app',
                     'probe-vulkan', 'probe-ahb'):
            path = prefix / 'bin' / name
            path.write_text(STUB)
            path.chmod(0o755)

    def run_launcher(self, *arguments, env=None, launcher=None):
        environment = dict(os.environ)
        environment.pop('PAD_GPU_PREFIX', None)
        environment.update(TEST_CHECKS=str(self.checks))
        environment.update(env or {})
        return subprocess.run(['bash', '-c', HARNESS, 'test-launcher',
                               str(launcher or self.launcher), *map(str, arguments)],
                              env=environment, text=True, capture_output=True, timeout=10)

    def data(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_custom_prefix_is_derived_from_installed_launcher(self):
        data = self.data(self.run_launcher('auto', self.prefix / 'bin/app', 'one two', '--literal=$x'))
        self.assertEqual(data['argv'], ['one two', '--literal=$x'])
        self.assertEqual(data['env']['VK_DRIVER_FILES'], str(self.prefix / 'share/vulkan/icd.d/sysvk_icd.json'))
        self.assertEqual(data['env']['HYBRIS_VULKANPLATFORM'], 'null')
        self.assertEqual(self.checks.read_text(), 'android:1\nx11\n')

    def test_launcher_symlink_uses_target_installation(self):
        link = self.prefix / 'gpu-link'
        link.symlink_to(self.launcher)
        result = self.run_launcher('info', launcher=link)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('prefix=' + str(self.prefix), result.stdout)

    def test_explicit_prefix_override_is_respected(self):
        with tempfile.TemporaryDirectory(prefix='pad-gpu-launcher-override.', dir='/opt') as other:
            self.make_install(Path(other))
            data = self.data(self.run_launcher('auto', self.prefix / 'bin/app', env={'PAD_GPU_PREFIX': other}))
            self.assertEqual(data['env']['VK_DRIVER_FILES'], other + '/share/vulkan/icd.d/sysvk_icd.json')

    def test_auto_only_adds_angle_arguments_to_known_executables(self):
        for name in ('chromium', 'electron42'):
            with self.subTest(name=name):
                data = self.data(self.run_launcher('auto', self.prefix / 'bin' / name, '--user-data-dir=/tmp/test'))
                self.assertIn('--use-angle=vulkan', data['argv'])
                self.assertIn('--disable-software-rasterizer', data['argv'])
                self.assertEqual(data['argv'][-1], '--user-data-dir=/tmp/test')
        data = self.data(self.run_launcher('auto', self.prefix / 'bin/electron42-unknown'))
        self.assertEqual(data['argv'], [])

    def test_auto_detects_renamed_packaged_and_unpacked_electron(self):
        for application in ('resources/app.asar', 'resources/app/package.json'):
            with self.subTest(application=application):
                directory = self.prefix / ('packed' if application.endswith('.asar') else 'unpacked')
                directory.mkdir()
                binary = directory / 'renamed-editor'
                shutil.copy2(self.prefix / 'bin/app', binary)
                (directory / 'icudtl.dat').touch()
                bundle = directory / application
                bundle.parent.mkdir(parents=True)
                bundle.touch()
                data = self.data(self.run_launcher('auto', binary, '--example'))
                self.assertIn('--use-angle=vulkan', data['argv'])
                self.assertEqual(data['argv'][-1], '--example')
                software = self.data(self.run_launcher('--software', 'auto', binary))
                self.assertIn('--disable-gpu', software['argv'])
                # Explicit native routes continue to avoid all browser arguments.
                for mode in ('gl', 'vulkan'):
                    self.assertEqual(self.data(self.run_launcher(mode, binary))['argv'], [])

    def test_resources_or_icu_alone_do_not_classify_native_apps_as_electron(self):
        cases = ((True, None), (False, None), (False, 'app.asar'), (False, 'app/package.json'))
        for index, (icu, application) in enumerate(cases):
            with self.subTest(icu=icu, application=application):
                directory = self.prefix / ('native-' + str(index))
                (directory / 'resources').mkdir(parents=True)
                binary = directory / 'native-qt-or-vulkan-app'
                shutil.copy2(self.prefix / 'bin/app', binary)
                if icu:
                    (directory / 'icudtl.dat').touch()
                if application:
                    bundle = directory / 'resources' / application
                    bundle.parent.mkdir(parents=True, exist_ok=True)
                    bundle.touch()
                self.assertEqual(self.data(self.run_launcher('auto', binary, '--native'))['argv'], ['--native'])

    def test_electron_distribution_detection_follows_executable_symlink(self):
        directory = self.prefix / 'distribution'
        (directory / 'resources').mkdir(parents=True)
        binary = directory / 'renamed-app'
        shutil.copy2(self.prefix / 'bin/app', binary)
        (directory / 'icudtl.dat').touch()
        (directory / 'resources/app.asar').touch()
        link = self.prefix / 'bin/custom-app'
        link.symlink_to(binary)
        self.assertIn('--use-angle=vulkan', self.data(self.run_launcher('auto', link))['argv'])

    def test_gl_and_vulkan_do_not_inject_browser_flags(self):
        for mode in ('gl', 'vulkan'):
            with self.subTest(mode=mode):
                data = self.data(self.run_launcher(mode, self.prefix / 'bin/fake app', '--test'))
                self.assertEqual(data['argv'], ['--test'])
                self.assertEqual(data['env']['GALLIUM_DRIVER'], 'zink')

    def test_explicit_electron_and_legacy_aliases_keep_angle_route(self):
        for mode in ('electron', 'chromium', 'trae', 'chatgpt'):
            with self.subTest(mode=mode):
                args = [mode, self.prefix / 'bin/app'] if mode == 'electron' else [mode]
                data = self.data(self.run_launcher(*args, '--example',
                    env={'MOCK_ALIAS_BINARY': str(self.prefix / 'bin/app')}))
                self.assertIn('--use-angle=vulkan', data['argv'])
                self.assertEqual(data['argv'][-1], '--example')

    def test_inherited_graphics_environment_is_removed_but_app_settings_survive(self):
        inherited = {'VK_INSTANCE_LAYERS': 'old', 'VK_ADD_DRIVER_FILES': '/wrong/icd.json',
                     'HYBRIS_LINKER_DIR': '/old/linker', 'LD_LIBRARY_PATH': '/old/lib',
                     'DISABLE_WSI_LAYER': '1', 'LIBGL_ALWAYS_SOFTWARE': '1', 'vblank_mode': '0',
                     'SENTINEL_APP_SETTING': 'preserved'}
        data = self.data(self.run_launcher('auto', self.prefix / 'bin/app', env=inherited))
        for key in inherited.keys() - {'SENTINEL_APP_SETTING'}:
            self.assertIsNone(data['env'][key], key)
        self.assertEqual(data['env']['SENTINEL_APP_SETTING'], 'preserved')

    def test_wrong_icd_prefix_and_missing_wsi_fail_before_launch(self):
        manifest = self.prefix / 'share/vulkan/icd.d/sysvk_icd.json'
        manifest.write_text(json.dumps({'ICD': {'library_path': '/opt/pad7spro-gpu/lib/libsysvk.so'}}))
        result = self.run_launcher('auto', self.prefix / 'bin/app')
        self.assertEqual(result.returncode, 78)
        self.assertEqual(result.stdout, '')
        self.assertIn('wrong or missing library', result.stderr)
        manifest.write_text(json.dumps({'ICD': {'library_path': str(self.prefix / 'lib/libsysvk.so')}}))
        (self.prefix / 'share/vulkan/implicit_layer.d/libVkLayer_window_system_integration.so').unlink()
        result = self.run_launcher('gl', self.prefix / 'bin/app')
        self.assertEqual(result.returncode, 78)
        self.assertEqual(result.stdout, '')

    def test_library_symlink_outside_prefix_is_rejected(self):
        library = self.prefix / 'lib/libahb-wrapper.so.1'
        library.unlink()
        library.symlink_to('/bin/true')
        result = self.run_launcher('auto', self.prefix / 'bin/app')
        self.assertEqual(result.returncode, 78)
        self.assertIn('escapes prefix', result.stderr)

    def test_hardware_failure_does_not_launch_or_retry_software(self):
        result = self.run_launcher('auto', self.prefix / 'bin/app', env={'MOCK_ANDROID_FAIL': '1'})
        self.assertEqual(result.returncode, 78)
        self.assertEqual(result.stdout, '')
        self.assertEqual(self.checks.read_text(), 'android:1\n')

    def test_explicit_software_does_not_need_bridge_or_android(self):
        shutil.rmtree(self.prefix / 'lib')
        data = self.data(self.run_launcher('--software', 'auto', self.prefix / 'bin/chromium',
                                          env={'MOCK_ANDROID_FAIL': '1'}))
        self.assertEqual(data['env']['LIBGL_ALWAYS_SOFTWARE'], '1')
        self.assertEqual(data['env']['GALLIUM_DRIVER'], 'llvmpipe')
        self.assertIsNone(data['env']['HYBRIS_LD_LIBRARY_PATH'])
        self.assertNotIn(str(self.prefix), data['env']['VK_DRIVER_FILES'])
        self.assertIn('--disable-gpu', data['argv'])
        self.assertNotIn('--use-angle=vulkan', data['argv'])
        self.assertEqual(self.checks.read_text(), 'x11\n')

    def test_headless_probe_and_ahb_check_only_relevant_prerequisites(self):
        shutil.rmtree(self.prefix / 'share/vulkan/implicit_layer.d')
        for mode, expected in (('probe', 'android:0\n'), ('ahb', 'android:1\n')):
            with self.subTest(mode=mode):
                self.checks.unlink(missing_ok=True)
                self.data(self.run_launcher(mode))
                self.assertEqual(self.checks.read_text(), expected)
        self.checks.unlink()
        self.data(self.run_launcher('--headless', 'vulkan', self.prefix / 'bin/app'))
        self.assertEqual(self.checks.read_text(), 'android:0\n')

    def test_conflicting_renderer_arguments_are_rejected(self):
        for args in (('auto', '--use-angle=gl-egl'), ('auto', '--disable-gpu')):
            result = self.run_launcher(args[0], self.prefix / 'bin/chromium', args[1])
            self.assertEqual(result.returncode, 78)
            self.assertIn('conflicts', result.stderr)
        result = self.run_launcher('--software', 'auto', self.prefix / 'bin/chromium', '--enable-gpu')
        self.assertEqual(result.returncode, 78)

    def test_target_exit_status_is_preserved(self):
        result = self.run_launcher('auto', self.prefix / 'bin/app', env={'TEST_EXIT': '23'})
        self.assertEqual(result.returncode, 23)

    def test_doctor_checks_all_modules_and_returns_failure(self):
        result = self.run_launcher('doctor', env={'MOCK_ANDROID_FAIL': '1', 'MOCK_READELF': '1'})
        self.assertEqual(result.returncode, 78)
        self.assertIn('core files/manifests: OK', result.stderr)
        self.assertIn('wsi files/manifests: OK', result.stderr)
        self.assertEqual(self.checks.read_text(), 'android:1\nx11\n')

    def test_info_does_not_need_hardware_and_rejects_invalid_pid(self):
        result = self.run_launcher('info', env={'MOCK_ANDROID_FAIL': '1', 'MOCK_X11_FAIL': '1'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.checks.exists())
        self.assertEqual(self.run_launcher('info', '../1').returncode, 78)

    def test_help_and_invalid_prefix(self):
        result = subprocess.run(['bash', str(self.launcher), '--help'], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for prefix in ('/opt/..', '/opt/.', '/tmp/bridge', '/opt/a/b'):
            with self.subTest(prefix=prefix):
                self.assertEqual(self.run_launcher('info', env={'PAD_GPU_PREFIX': prefix}).returncode, 64)


if __name__ == '__main__':
    unittest.main()
