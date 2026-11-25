#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read-only, bounded r3.5 X11 stall recorder. Never wakes/restarts/reconfigures X11.

Must run as root inside the tablet chroot. Offsets are specific to the exact
final arm64 APK and are checked against the APK hash and loaded ELF header.
Samples are not coherent transactions and are NOT a physical FPS measurement.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import time
import zipfile


APK_SHA256 = '88346b5831c33e585d467bbf0f8255b972a05dca1ffb112a03bf683404625411'
NATIVE_SHA256 = 'b82d6c7977ad3a5f8e26cbda26126cba5de31bd3e6ede539768e424fbad6eb08'
# nm + DWARF from the byte-identical final native ELF, not a guessed struct ABI.
GLOBALS = {'frame_callback_pending': (0x369500, 'I'),
           'frame_work_queued': (0x369504, 'I'),
           'latest_tick_ns': (0x369508, 'Q'), 'max_fps': (0x369478, 'I')}
SHARED = {'locking_pid': (40, 'i'), 'copy_write': (48, 'I'),
          'copy_read': (52, 'I'), 'copy_completed': (56, 'Q'),
          'copy_failed': (64, 'Q'), 'root_buffer': (1352, 'Q'),
          'draw_requested': (1360, 'B'), 'surface_available': (1361, 'B'),
          'waiting_for_tick': (1362, 'B'), 'rendered_frames': (1364, 'I')}


def starttime(pid):
    return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]


def find_server():
    found = []
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            args = (proc / 'cmdline').read_bytes().split(b'\0')
            if b'termux-x11 com.termux.x11' in args[0] or (
                    args[0].endswith(b'termux-x11') and b'com.termux.x11' in args):
                found.append(int(proc.name))
        except (OSError, IndexError):
            continue
    if len(found) != 1:
        raise ValueError(f'expected exactly one X server, found {found}; use --pid')
    return found[0]


def parse_maps(text):
    return [line.split(None, 5) for line in text.splitlines() if len(line.split(None, 5)) == 6]


def open_mapped_apk(pid, row, proc_root=Path('/proc')):
    """Read the actual backing inode, including a still-mapped replaced APK."""
    process = proc_root / str(pid)
    path = (process / 'map_files' / row[0] if row[5].endswith(' (deleted)') else
            process / 'root' / row[5].lstrip('/'))
    stream = path.open('rb')
    identity = os.fstat(stream.fileno())
    device = tuple(int(value, 16) for value in row[3].split(':'))
    if (identity.st_ino != int(row[4]) or
            (os.major(identity.st_dev), os.minor(identity.st_dev)) != device):
        stream.close()
        raise ValueError('mapped APK inode/device changed; refusing stale identity')
    return stream


def identify(pid):
    generation = starttime(pid)
    rows = parse_maps(Path(f'/proc/{pid}/maps').read_text())
    shared = [r for r in rows if r[1] == 'rw-s' and r[5] == '/dev/ashmem/xserver (deleted)']
    code = [r for r in rows if 'x' in r[1] and '/com.termux.x11-' in r[5]
            and r[5].removesuffix(' (deleted)').endswith('/base.apk')]
    # Android may rename an unlinked package directory to UUID==deleted==.
    code += [r for r in rows if 'x' in r[1] and r[5].endswith('/base.apk (deleted)')
             and r not in code and '==deleted==' in r[5]]
    if len(shared) != 1 or len(code) != 1:
        raise ValueError('missing/ambiguous final APK or shared-state mapping')
    with open_mapped_apk(pid, code[0]) as stream:
        apk_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
        if apk_hash != APK_SHA256:
            raise ValueError('unsupported APK; refusing to read version-specific offsets')
        with zipfile.ZipFile(stream) as z:
            entry = z.getinfo('lib/arm64-v8a/libXlorie.so')
            native = z.read(entry)
        stream.seek(entry.header_offset + 26)
        name_len, extra_len = struct.unpack('<HH', stream.read(4))
    if hashlib.sha256(native).hexdigest() != NATIVE_SHA256:
        raise ValueError('native library hash mismatch')
    zip_offset = entry.header_offset + 30 + name_len + extra_len
    if int(code[0][2], 16) != zip_offset or entry.compress_type != zipfile.ZIP_STORED:
        raise ValueError('unexpected native load mapping')
    base = int(code[0][0].split('-')[0], 16)
    shared_base, shared_end = [int(x, 16) for x in shared[0][0].split('-')]
    if shared_end - shared_base < 0x1005a0:
        raise ValueError('shared state is too small for final ABI')
    fd = os.open(f'/proc/{pid}/mem', os.O_RDONLY)
    try:
        if os.pread(fd, 256, base) != native[:256] or starttime(pid) != generation:
            raise ValueError('loaded ELF/generation mismatch')
    except BaseException:
        os.close(fd)
        raise
    return fd, base, shared_base, generation


def sample(fd, base, shared_base):
    result = {'monotonic_ns': time.monotonic_ns()}
    for group, address in [(GLOBALS, base), (SHARED, shared_base)]:
        for name, (offset, fmt) in group.items():
            raw = os.pread(fd, struct.calcsize(fmt), address + offset)
            result[name] = struct.unpack('<' + fmt, raw)[0]
    result['tick_age_ms'] = (result['monotonic_ns'] - result['latest_tick_ns']) / 1e6
    return result


def freezer_state(pid, proc_root=Path('/proc')):
    """Inspect cgroup v2 ancestors: a process leaf may inherit a UID freeze.

    Unreadable/missing data is unknown, never proof that the process is thawed.
    Android's cgroup tree is resolved through the target's mount namespace.
    """
    result = {'frozen': None, 'freeze_requested': None, 'ancestors': []}
    try:
        rows = (proc_root / str(pid) / 'cgroup').read_text().splitlines()
        relative = next(line[3:] for line in rows if line.startswith('0::'))
        if not relative.startswith('/') or '..' in Path(relative).parts:
            raise ValueError('unexpected cgroup path')
        mount = proc_root / str(pid) / 'root/sys/fs/cgroup'
        path = Path(relative.lstrip('/'))
        # The root cgroup cannot be frozen and has no cgroup.freeze file.
        while path != Path('.'):
            directory = mount / path
            request = (directory / 'cgroup.freeze').read_text().strip()
            events = dict(line.split() for line in (directory / 'cgroup.events').read_text().splitlines())
            if request not in ('0', '1') or events.get('frozen') not in ('0', '1'):
                raise ValueError('unexpected freezer state')
            result['ancestors'].append({'path': '/' + str(path) if str(path) != '.' else '/',
                                        'freeze': int(request), 'frozen': int(events['frozen'])})
            path = path.parent
        result['frozen'] = any(r['frozen'] for r in result['ancestors'])
        result['freeze_requested'] = any(r['freeze'] for r in result['ancestors'])
    except (OSError, StopIteration, ValueError) as e:
        # Even if a parent/root is unreadable, positive evidence remains valid.
        if any(r['frozen'] for r in result['ancestors']):
            result['frozen'] = True
        if any(r['freeze'] for r in result['ancestors']):
            result['freeze_requested'] = True
        result['error'] = str(e)
    return result


class StallDetector:
    """Flags pending work without frame progress, never a static desktop alone."""
    def __init__(self, seconds=2):
        self.seconds = seconds
        self.frames = None
        self.since = None

    def update(self, row):
        pending = row['draw_requested'] or row['copy_write'] != row['copy_read']
        now = row['monotonic_ns'] / 1e9
        if not row['surface_available'] or not pending or row['rendered_frames'] != self.frames:
            self.since = now
        self.frames = row['rendered_frames']
        if self.since is None:
            self.since = now
        return bool(row['surface_available'] and pending and now - self.since >= self.seconds)


def threads(pid):
    result = []
    for thread in Path(f'/proc/{pid}/task').glob('*'):
        row = {'tid': thread.name}
        for name in ('comm', 'wchan', 'syscall', 'stack'):
            try:
                row[name] = (thread / name).read_text()
            except OSError as e:
                row[name] = str(e)
        result.append(row)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int)
    parser.add_argument('--renderer-pid', type=int)
    parser.add_argument('--seconds', type=float, default=120)
    parser.add_argument('--interval', type=float, default=0.2)
    parser.add_argument('--output', type=Path, required=True, help='NEW private directory')
    args = parser.parse_args(argv)
    if not 0 < args.seconds <= 1800 or not 0.1 <= args.interval <= 5:
        parser.error('duration must be 0..1800s and interval 0.1..5s')
    pid = args.pid or find_server()
    fd, base, shared_base, generation = identify(pid)
    created = False
    try:
        renderer_generation = starttime(args.renderer_pid) if args.renderer_pid else None
        args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
        created = True
        metadata = dict(pid=pid, starttime=generation, apk_sha256=APK_SHA256,
                        native_sha256=NATIVE_SHA256, base=hex(base), shared_base=hex(shared_base),
                        seconds=args.seconds, interval=args.interval, read_only=True,
                        caveat='Asynchronous internal counters, not screen FPS; no screenshots or input.')
        (args.output / 'metadata.json').write_text(json.dumps(metadata, indent=2))
        detector = StallDetector()
        deadline = time.monotonic() + args.seconds
        flagged = 0
        with (args.output / 'samples.jsonl').open('x') as out:
            while time.monotonic() < deadline:
                if starttime(pid) != generation:
                    raise ValueError('server exited or PID reused; capture invalidated')
                row = sample(fd, base, shared_base)
                row['freezer'] = freezer_state(pid)
                stalled = detector.update(row)
                row['pending_work_stall_candidate'] = stalled
                if (stalled or row['freezer']['frozen'] is True) and flagged < 3:
                    snapshot = {'server': threads(pid)}
                    if args.renderer_pid:
                        if starttime(args.renderer_pid) != renderer_generation:
                            raise ValueError('renderer exited or PID reused; capture invalidated')
                        snapshot['renderer'] = threads(args.renderer_pid)
                    (args.output / f'stall-{flagged}.json').write_text(json.dumps(snapshot, indent=2))
                    flagged += 1
                out.write(json.dumps(row) + '\n')
                out.flush()
                time.sleep(min(args.interval, max(0, deadline - time.monotonic())))
        summary = dict(completed=True, stall_snapshots=flagged,
                       caveat='No candidate does NOT prove the reported freeze is fixed.')
        (args.output / 'summary.json').write_text(json.dumps(summary, indent=2))
        print(json.dumps(summary))
    except (OSError, ValueError, struct.error) as e:
        if created and not (args.output / 'summary.json').exists():
            (args.output / 'summary.json').write_text(json.dumps(
                dict(completed=False, error=str(e), caveat='Incomplete capture; not acceptance.'), indent=2))
        raise
    finally:
        os.close(fd)


if __name__ == '__main__':
    main()
