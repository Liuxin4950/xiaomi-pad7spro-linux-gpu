import importlib.util
from pathlib import Path
import unittest
import tempfile
import os
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('stall', ROOT / 'scripts/capture-x11-stall.py')
stall = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stall)


class StallTests(unittest.TestCase):
    def test_deleted_apk_uses_actual_mapping_not_current_package(self):
        with tempfile.TemporaryDirectory() as directory:
            proc = Path(directory)
            original = proc / 'old.apk'
            original.write_bytes(b'old mapped package')
            current = proc / '123/root/package/base.apk'
            current.parent.mkdir(parents=True)
            current.write_bytes(b'new installed package')
            mapping = proc / '123/map_files/1000-2000'
            mapping.parent.mkdir()
            mapping.symlink_to(original)
            identity = original.stat()
            row = ['1000-2000', 'r-xp', '0000',
                   f'{os.major(identity.st_dev):x}:{os.minor(identity.st_dev):x}',
                   str(identity.st_ino), '/package/base.apk (deleted)']
            with stall.open_mapped_apk(123, row, proc) as stream:
                self.assertEqual(stream.read(), b'old mapped package')
            mapping.unlink()
            mapping.symlink_to(current)
            with self.assertRaisesRegex(ValueError, 'inode/device changed'):
                stall.open_mapped_apk(123, row, proc)

    def test_normal_apk_requires_matching_mapping_inode(self):
        with tempfile.TemporaryDirectory() as directory:
            proc = Path(directory)
            apk = proc / '123/root/package/base.apk'
            apk.parent.mkdir(parents=True)
            apk.write_bytes(b'package')
            identity = apk.stat()
            row = ['1000-2000', 'r-xp', '0000',
                   f'{os.major(identity.st_dev):x}:{os.minor(identity.st_dev):x}',
                   str(identity.st_ino + 1), '/package/base.apk']
            with self.assertRaisesRegex(ValueError, 'inode/device changed'):
                stall.open_mapped_apk(123, row, proc)

    def test_parent_freeze_is_detected_even_when_leaf_request_is_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            proc = Path(directory)
            (proc / '123').mkdir()
            (proc / '123/cgroup').write_text('0::/apps/uid_10305/pid_13766\n')
            base = proc / '123/root/sys/fs/cgroup'
            for relative, freeze, frozen in [('', 0, 0), ('apps', 0, 0),
                    ('apps/uid_10305', 1, 1), ('apps/uid_10305/pid_13766', 0, 1)]:
                path = base / relative
                path.mkdir(parents=True, exist_ok=True)
                (path / 'cgroup.freeze').write_text(str(freeze))
                (path / 'cgroup.events').write_text(f'populated 1\nfrozen {frozen}\n')
            state = stall.freezer_state(123, proc)
            self.assertTrue(state['frozen'])
            self.assertTrue(state['freeze_requested'])
            self.assertEqual(len(state['ancestors']), 3)
            self.assertNotIn('error', state)

    def test_unreadable_freezer_is_unknown_not_thawed(self):
        with tempfile.TemporaryDirectory() as directory:
            state = stall.freezer_state(123, Path(directory))
            self.assertIsNone(state['frozen'])
            self.assertIn('error', state)

    def row(self, seconds, frames=10, draw=1, surface=1, write=2, read=2):
        return dict(monotonic_ns=seconds * 10**9, rendered_frames=frames,
                    draw_requested=draw, surface_available=surface, copy_write=write, copy_read=read)

    def test_static_desktop_is_not_a_stall(self):
        d = stall.StallDetector()
        for seconds in range(10):
            self.assertFalse(d.update(self.row(seconds, draw=0)))

    def test_hidden_surface_is_not_a_stall(self):
        d = stall.StallDetector()
        for seconds in range(10):
            self.assertFalse(d.update(self.row(seconds, surface=0)))

    def test_pending_draw_and_copy_without_frames_detected(self):
        for draw, write in [(1, 2), (0, 3)]:
            d = stall.StallDetector()
            self.assertFalse(d.update(self.row(0, draw=draw, write=write)))
            self.assertFalse(d.update(self.row(1, draw=draw, write=write)))
            self.assertTrue(d.update(self.row(2, draw=draw, write=write)))

    def test_resumed_frames_or_counter_reset_clears_timer(self):
        d = stall.StallDetector()
        d.update(self.row(0))
        self.assertTrue(d.update(self.row(3)))
        self.assertFalse(d.update(self.row(4, frames=0)))
        self.assertFalse(d.update(self.row(5, frames=1)))

    def test_arguments_validated_before_process_access(self):
        with patch.object(stall, 'find_server') as probe:
            with self.assertRaises(SystemExit):
                stall.main(['--seconds', '999999', '--output', '/unused'])
            probe.assert_not_called()


if __name__ == '__main__':
    unittest.main()
