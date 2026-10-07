#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Bounded Trae startup recovery for an early Oilpan address reservation failure.

This preserves the GPU route and application arguments. One retry is allowed only
when the selected profile has no live or ambiguous singleton owner, and no GPU,
renderer, utility or JavaScript initialization was observed. Profile files are
never edited. No ASLR, memory limit, V8 or sandbox flags are changed.
"""
import os
from pathlib import Path
import selectors
import signal
import socket
import subprocess
import sys
import time


TRAE_BINARY = '/usr/share/trae-cn/trae-cn'
FATAL = b'Fatal process out of memory: Oilpan: CagedHeap reservation.'
STARTUP_SECONDS = 8.0
JS_MARKERS = (b'ProcessMonitor constructor', b'No config file found', b'(node:',
              b'DevTools listening', b'lifecycle (main)', b'TRAE Config IPC')


def diagnostic(message):
    print('[pad-gpu] ' + message, file=sys.stderr, flush=True)


def profile_argument(arguments, cwd=None):
    selected = None
    for index, argument in enumerate(arguments):
        if argument.startswith('--user-data-dir='):
            selected = argument.partition('=')[2]
        elif argument == '--user-data-dir' and index + 1 < len(arguments):
            selected = arguments[index + 1]
    if not selected:
        return None
    path = Path(selected)
    return ((Path(cwd) / path) if cwd and not path.is_absolute() else path).resolve()


def default_profile(environment):
    config = environment.get('XDG_CONFIG_HOME')
    if config and not Path(config).is_absolute():
        raise ValueError('relative XDG_CONFIG_HOME')
    return ((Path(config) if config else Path(environment['HOME']) / '.config') / 'Trae CN').resolve()


def profile_can_retry(binary, arguments):
    try:
        profile = profile_argument(arguments) or default_profile(os.environ)
        if profile.exists() and not profile.is_dir():
            return False, 'profile is not a directory'
        for name in ('SingletonLock', 'SingleInstanceLock', 'SingleInstance'):
            lock = profile / name
            if not lock.exists() and not lock.is_symlink():
                continue
            if not lock.is_symlink():
                return False, 'ambiguous singleton lock: ' + name
            target = str(lock.readlink())
            hostname, _, owner = target.rpartition('-')
            if hostname != socket.gethostname():
                return False, 'singleton lock belongs to a different or unknown host'
            if not owner.isdecimal():
                return False, 'unrecognized singleton lock owner'
            owner_root = Path('/proc/' + owner)
            if owner_root.exists():
                # A reused PID also blocks recovery; do not guess ownership.
                state = (owner_root / 'stat').read_text().rsplit(')', 1)[1].split()[0]
                if state != 'Z':
                    return False, 'live singleton lock owner PID ' + owner
        singleton_socket = profile / 'SingletonSocket'
        if singleton_socket.exists():
            return False, 'singleton socket is still present'
        # Do not restart a request that could be handed to another running app.
        executable = str(Path(binary).resolve())
        for entry in Path('/proc').iterdir():
            if not entry.name.isdecimal() or int(entry.name) == os.getpid():
                continue
            try:
                command = (entry / 'cmdline').read_bytes().split(b'\0')
                decoded = [part.decode(errors='surrogateescape') for part in command if part]
                if executable not in decoded:
                    continue
                candidate = profile_argument(decoded[1:], (entry / 'cwd').resolve())
                if candidate is None:
                    environment = dict(part.decode(errors='surrogateescape').split('=', 1)
                                       for part in (entry / 'environ').read_bytes().split(b'\0') if b'=' in part)
                    candidate = default_profile(environment)
                if candidate == profile:
                    return False, 'another process already uses this profile'
            except FileNotFoundError:
                continue
            except (OSError, ValueError, KeyError):
                return False, 'cannot verify profile ownership'
    except (OSError, ValueError, KeyError):
        return False, 'cannot verify singleton state'
    return True, 'no live singleton owner found'


def process_identity(pid):
    text = Path('/proc/' + str(pid) + '/stat').read_text()
    return text[text.rfind(')') + 2:].split()[19]


def owned_tree(pid, expected_identity):
    """Find only descendants of our own newly spawned Trae process."""
    # Android kernels may omit /proc/PID/task/TID/children. Procps can still
    # snapshot parent PIDs without ptrace, GPU hooks or a permanent monitor.
    try:
        if expected_identity is None or process_identity(pid) != expected_identity:
            return None
        snapshot = subprocess.run(['/usr/bin/ps', '-eo', 'pid=,ppid='],
                                  capture_output=True, text=True, check=True, timeout=1)
        children = {}
        for line in snapshot.stdout.splitlines():
            child, parent = map(int, line.split())
            children.setdefault(parent, []).append(child)
    except (OSError, IndexError, ValueError, subprocess.SubprocessError):
        return None  # Unknown ownership disables recovery.
    found, queue = {}, [pid]
    while queue:
        current = queue.pop()
        if current in found:
            continue
        try:
            root = Path('/proc/' + str(current))
            identity = process_identity(current)
            if current == pid and identity != expected_identity:
                return None
            command = (root / 'cmdline').read_bytes().split(b'\0')
            found[current] = (identity, command)
            queue.extend(children.get(current, []))
        except (OSError, IndexError):
            continue
    return found


def stop_owned_tree(process, observed, root_identity):
    # Never refresh the root identity after wait()/poll(): the PID may already
    # belong to an unrelated process. Expansion validates the launch identity
    # both before taking the snapshot and while reading its root record.
    observed.update(owned_tree(process.pid, root_identity) or {})
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid, (identity, _) in reversed(list(observed.items())):
            if pid == os.getpid():
                continue
            try:
                if process_identity(pid) == identity:
                    os.kill(pid, sig)
            except (OSError, IndexError):
                pass
        try:
            process.wait(timeout=.6)
        except subprocess.TimeoutExpired:
            pass
        deadline = time.monotonic() + .6
        while True:
            live = False
            for pid, (identity, _) in observed.items():
                try:
                    text = Path('/proc/' + str(pid) + '/stat').read_text()
                    fields = text[text.rfind(')') + 2:].split()
                    if fields[19] == identity and fields[0] not in ('Z', 'X'):
                        live = True
                except FileNotFoundError:
                    continue
                except (OSError, IndexError):
                    live = True
            if not live:
                return True
            if time.monotonic() >= deadline:
                break
            time.sleep(.025)
    return False


def run_attempt(binary, arguments):
    try:
        profile = profile_argument(arguments) or default_profile(os.environ)
    except (ValueError, KeyError):
        profile = None
    # Creation of application logs or GPU caches also blocks recovery if a
    # short-lived child escaped a process snapshot. Never inspect their content.
    milestones = [profile / name for name in ('logs', 'GPUCache', 'DawnGraphiteCache', 'DawnWebGPUCache')] if profile else []
    baseline = {}
    for path in milestones:
        try:
            baseline[path] = path.stat().st_mtime_ns
        except FileNotFoundError:
            baseline[path] = None
        except OSError:
            baseline[path] = 'unknown'
    process = subprocess.Popen([binary, *arguments], stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT)
    try:
        root_identity = process_identity(process.pid)
    except (OSError, IndexError):
        root_identity = None
    observed = ({process.pid: (root_identity, [])} if root_identity is not None else {})
    retained = b''
    stage_started, fatal = profile is None, False
    deadline = time.monotonic() + STARTUP_SECONDS
    next_scan = 0.0
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    old_handlers = {}

    def interrupted(signum, _frame):
        try:
            process.send_signal(signum)
        except ProcessLookupError:
            pass
        raise SystemExit(128 + signum)

    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        old_handlers[sig] = signal.signal(sig, interrupted)
    try:
        while True:
            startup = time.monotonic() < deadline
            if startup and not stage_started and time.monotonic() >= next_scan:
                current = owned_tree(process.pid, root_identity)
                next_scan = time.monotonic() + .25
                observed.update(current or {})
                stage_started = current is None or any(
                    argument in (b'--type=gpu-process', b'--type=renderer', b'--type=utility')
                    for _, command in (current or {}).values() for argument in command)
            events = selector.select(.05 if startup and not stage_started else .5)
            if events:
                chunk = os.read(process.stdout.fileno(), 8192)
                if not chunk:
                    if process.poll() is not None:
                        break
                    selector.unregister(process.stdout)
                else:
                    sys.stderr.buffer.write(chunk)
                    sys.stderr.buffer.flush()
                    retained = (retained + chunk)[-16384:]
                    if any(marker in retained for marker in JS_MARKERS):
                        stage_started = True
                    if startup and not stage_started and FATAL in retained:
                        # Recheck immediately before terminating a failed startup.
                        current = owned_tree(process.pid, root_identity)
                        observed.update(current or {})
                        stage_started = current is None or any(
                            argument in (b'--type=gpu-process', b'--type=renderer', b'--type=utility')
                            for _, command in (current or {}).values() for argument in command)
                        for path in milestones:
                            try:
                                if path.stat().st_mtime_ns != baseline[path]:
                                    stage_started = True
                            except FileNotFoundError:
                                if baseline[path] is not None:
                                    stage_started = True
                            except OSError:
                                stage_started = True
                        if not stage_started:
                            fatal = True
                            break
            elif process.poll() is not None:
                break
        if fatal:
            return 70, True
        status = process.wait()
        return (status if status >= 0 else 128 - status), False
    finally:
        selector.close()
        stopped = stop_owned_tree(process, observed, root_identity)
        process.stdout.close()
        for sig, previous in old_handlers.items():
            signal.signal(sig, previous)
        if not stopped:
            raise OSError('Trae child cleanup could not be confirmed; refusing startup retry')


def launch(binary, arguments):
    eligible, reason = profile_can_retry(binary, arguments)
    for attempt in range(2):
        status, early_fatal = run_attempt(binary, arguments)
        if not early_fatal:
            if status:
                diagnostic('Trae exited with status ' + str(status) + '; no startup retry.')
            return status
        if attempt == 0 and eligible:
            diagnostic('Trae hit the exact early Oilpan cage reservation failure before any GPU/renderer/utility process was observed.')
            # Check again after the failed child tree is gone, before launching.
            eligible, reason = profile_can_retry(binary, arguments)
            if not eligible:
                diagnostic('Trae startup failed; retry blocked: ' + reason + '; status=70.')
                return 70
            diagnostic('ASLR startup tolerance: retry 1/1 with a new process layout and the same unshared profile; this is not a GPU fix.')
        else:
            reason = 'retry already used' if attempt else reason
            diagnostic('Trae startup failed: Oilpan cage reservation; ' + reason + '. No further retry; status=70.')
            return 70
    return 70


def main():
    arguments = sys.argv[1:]
    if arguments and arguments[0] == '--':
        arguments = arguments[1:]
    if not arguments or Path(arguments[0]).resolve() != Path(TRAE_BINARY).resolve():
        diagnostic('usage: trae-start.py /usr/share/trae-cn/trae-cn [application arguments]')
        return 64
    try:
        return launch(arguments[0], arguments[1:])
    except OSError as error:
        diagnostic('Cannot start Trae: ' + str(error))
        return 78


if __name__ == '__main__':
    sys.exit(main())
