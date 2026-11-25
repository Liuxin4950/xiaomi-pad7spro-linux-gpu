"""Fault injection never touches the real root transport or active sessions."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMMON = ROOT / 'reference/termux/debian-shell.sh'


class SessionMonitorTests(unittest.TestCase):
    def test_actual_probe_uses_cached_pid_when_pidfile_disappears(self):
        common = COMMON.read_text()
        functions = common.split('# BEGIN session observation', 1)[1].split('\n', 1)[1].split('# END session observation', 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            library = temp / 'functions.sh'
            library.write_text(functions)
            pid = os.getpid()  # test runner, never the real desktop
            proc = Path(f'/proc/{pid}')
            generation = (proc / 'stat').read_text().rsplit(')', 1)[1].split()[19]
            env = dict(os.environ, LIBRARY=str(library), ROOTFS=os.readlink(proc / 'root'),
                       PID=str(pid), START=generation, MISSING=str(temp / 'nonexistent'))
            script = r'''
source "$LIBRARY"
safe_path() { [[ "$1" =~ ^/[[:alnum:]_.@%+,:=/-]+$ ]]; }
root() { bash -c "$1"; }
debian_session_status "$MISSING" "$PID" "$START"
debian_session_status "$MISSING" "$PID" 999999999999
debian_session_status "$MISSING" || echo missing-is-unknown
'''
            r = subprocess.run(['bash', '-c', script], env=env, text=True, capture_output=True, timeout=5)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.splitlines(), [f'alive:{pid}:{generation}', 'reused', 'missing-is-unknown'])

    def run_scenario(self, replies):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            common = COMMON.read_text()
            library = temp / 'monitor.sh'
            library.write_text(common.split('# BEGIN session observation', 1)[1].split('\n', 1)[1]
                               .split('# END session observation', 1)[0])
            (temp / 'replies').write_text('\n'.join(replies) + '\n')
            (temp / 'count').write_text('0')
            script = r'''
set -Eeuo pipefail
source "$LIBRARY"
debian_session_status() {
  n=$(cat "$TMP/count"); n=$((n+1)); echo "$n" >"$TMP/count"
  line=$(sed -n "${n}p" "$TMP/replies")
  [[ -n "$line" ]] || { echo 'test exhausted' >&2; exit 99; }
  printf '%s\n' "${line#*:}"
  return "${line%%:*}"
}
warn() { printf '%s\n' "$*" >>"$TMP/log"; }
sleep() { printf '%s\n' "$1" >>"$TMP/sleeps"; }
debian_wait_for_session /fake/session.pgid
'''
            result = subprocess.run(['bash', '-c', script], env={
                'PATH': '/usr/bin:/bin', 'TMP': str(temp), 'LIBRARY': str(library)
            }, text=True, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            return ((temp / 'log').read_text(), int((temp / 'count').read_text()),
                    (temp / 'sleeps').read_text() if (temp / 'sleeps').exists() else '')

    def test_transport_disconnect_is_not_session_death(self):
        log, probes, sleeps = self.run_scenario(['255:', '255:', '0:alive:123:456', '0:gone', '0:gone'])
        self.assertEqual(probes, 5)
        self.assertIn('NOT cleaning up', log)
        self.assertIn('recovered after 2', log)
        self.assertEqual(sleeps, '2\n4\n1\n')

    def test_partial_dead_reply_with_failure_does_not_authorize_cleanup(self):
        log, probes, _ = self.run_scenario(['255:gone', '0:alive:123:456', '0:gone', '0:gone'])
        self.assertEqual(probes, 4)
        self.assertIn('recovered after 1', log)

    def test_ambiguous_and_permission_error_replies_are_unknown(self):
        log, probes, _ = self.run_scenario(['74:', '0:unexpected', '0:alive:123:456', '0:gone', '0:gone'])
        self.assertEqual(probes, 5)
        self.assertIn('recovered after 2', log)

    def test_transient_missing_file_is_rechecked(self):
        log, probes, _ = self.run_scenario(['0:absent', '0:alive:123:456', '0:alive:123:456', '0:gone', '0:gone'])
        self.assertEqual(probes, 5)
        self.assertIn('recovered after 1', log)

    def test_confirmed_exit_finishes(self):
        for state in ['gone', 'wrong-root', 'reused']:
            log, probes, sleeps = self.run_scenario(['0:' + state, '0:' + state])
            self.assertEqual(probes, 2)
            self.assertEqual(sleeps, '')
            self.assertIn('two successful probes: ' + state, log)


if __name__ == '__main__':
    unittest.main()
