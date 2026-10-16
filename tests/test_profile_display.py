#!/usr/bin/env python3
"""Measurement failures must not produce apparently valid GPU results."""
import argparse
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('profile_display', ROOT / 'scripts/profile-display.py')
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)


class DisplayProfileTests(unittest.TestCase):
    def test_surface_selection_rejects_ambiguous_or_missing_layer(self):
        layer = 'SurfaceView[com.termux.x11/Main](BLAST)#1'
        self.assertEqual(profile.surface_layer(layer), layer)
        self.assertEqual(profile.surface_layer(layer + '\nSurfaceView[com.termux.x11/Main]#0\n'
                                              'Background for SurfaceView[com.termux.x11/Main]#2'), layer)
        with self.assertRaises(ValueError):
            profile.surface_layer(layer + '\n' + layer + '-other')
        self.assertEqual(profile.surface_layer(layer + '\nother', layer), layer)
        with self.assertRaises(ValueError):
            profile.surface_layer('other', layer)

    def test_timestamps_filter_ring_history_sentinels_and_duplicates(self):
        data = [dict(raw='16666666\n1 100 2\n1 120 2\n1 120 2\n1 0 2\n'
                         '1 9223372036854775807 2\n1 invalid 2\n1 300 2\n'), dict(error='missing')]
        self.assertEqual(profile.sf_timestamps(data, 110, 200), [120])

    def test_dimensions_are_from_target_display(self):
        with patch.object(profile.subprocess, 'check_output', return_value=' dimensions: 2736x1824 pixels') as call:
            self.assertEqual(profile.display_size(':7'), (2736, 1824))
            self.assertIn(':7', call.call_args.args[0])
        with patch.object(profile.subprocess, 'check_output', return_value='no display'):
            with self.assertRaises(ValueError):
                profile.display_size(':7')

    def test_identity_rejects_nonexecutables_and_tracks_actual_content(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory)
            (prefix / 'bin').mkdir()
            for name in ('gpu-run', 'probe-present'):
                (prefix / 'bin' / name).write_text('test')
            with self.assertRaises(ValueError):
                profile.release_identity(prefix)
            for name in ('gpu-run', 'probe-present'):
                (prefix / 'bin' / name).chmod(0o755)
            first = profile.release_identity(prefix)
            (prefix / 'bin/probe-present').write_text('changed')
            self.assertNotEqual(first['probe_sha256'], profile.release_identity(prefix)['probe_sha256'])

    def test_explicit_measurement_selection_required_before_device_access(self):
        with contextlib.redirect_stderr(io.StringIO()), patch.object(profile, 'device_conditions') as device:
            with self.assertRaises(SystemExit) as result:
                profile.main(['--output', '/must-not-be-created'])
            self.assertEqual(result.exception.code, 2)
            device.assert_not_called()

    def test_failed_probe_is_reported_and_static_mode_never_polls_sf(self):
        conditions = dict(brightness_setting='100', brightness_actual='.5', active_mode='1',
                          active_render_rate='60', screen_awake=True)
        options = argparse.Namespace(android_root=Path('/fake-android'), server_pid=None,
                                     surface_layer=None, sf_interval=1, trace=False, rate=0, fps=60)
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(profile, 'device_conditions', return_value=conditions), \
                patch.object(profile, 'find_server', return_value=(os.getpid(), [])), \
                patch.object(profile, 'frozen_state', return_value='0'), \
                patch.object(profile, 'android') as android:
            result = profile.run_case('failed-static', 'static', [sys.executable, '-c', 'raise SystemExit(9)'],
                                      Path(directory), dict(os.environ, DISPLAY=':1'), 2, options)
            self.assertEqual(result['rc'], 9)
            self.assertFalse(result['valid'])
            self.assertIn('client did not exit successfully', result['invalid_reasons'])
            self.assertTrue(any('timings' in reason for reason in result['invalid_reasons']))
            self.assertIsNone(result['actual_sf_presents'])
            self.assertFalse(result['sf_sampling_enabled'])
            android.assert_not_called()
            self.assertTrue((Path(directory) / 'failed-static/client.log').exists())


if __name__ == '__main__':
    unittest.main()
