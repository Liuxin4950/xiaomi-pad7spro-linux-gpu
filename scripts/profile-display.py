#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Bounded display checks; SF presents are not unique content FPS or input latency."""
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import threading
import time


def android(*args, root=Path('/proc/1/root')):
    command = shutil.which('chroot')
    if not command:
        raise RuntimeError('chroot unavailable')
    return subprocess.check_output([command, str(root), '/system/bin/' + args[0], *args[1:]],
                                   text=True, timeout=5)


def clocks():
    return dict(monotonic_ns=time.monotonic_ns(),
                boottime_ns=time.clock_gettime_ns(time.CLOCK_BOOTTIME), realtime_ns=time.time_ns())


def proc_cpu(pid):
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        return int(fields[19]), int(fields[11]) + int(fields[12])
    except (OSError, ValueError, IndexError):
        return None


def percent(values):
    values = sorted(values)
    return {f'p{q}': values[int((len(values) - 1) * q / 100)] for q in (50, 95, 99)} if values else {}


def release_identity(prefix):
    prefix = prefix.resolve(strict=True)
    for name in ('gpu-run', 'probe-present'):
        path = prefix / 'bin' / name
        if not path.is_file() or not os.access(path, os.X_OK):
            raise ValueError(f'missing executable: {path}')
    release, manifest = prefix / 'release.json', prefix / 'install-manifest.json'
    return dict(prefix=str(prefix), release=json.loads(release.read_text()) if release.is_file() else None,
                manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest() if manifest.is_file() else None,
                runner_sha256=hashlib.sha256((prefix / 'bin/gpu-run').read_bytes()).hexdigest(),
                probe_sha256=hashlib.sha256((prefix / 'bin/probe-present').read_bytes()).hexdigest())


def display_size(display):
    text = subprocess.check_output(['xdpyinfo', '-display', display], text=True, timeout=5)
    match = re.search(r'dimensions:\s+(\d+)x(\d+)\s+pixels', text)
    if not match:
        raise ValueError('cannot determine X11 dimensions; specify --width and --height')
    return tuple(map(int, match.groups()))


def find_server(display, requested=None):
    servers, tracked = [], []
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            args = path.joinpath('cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace').split()
            if not args:
                continue
            name = Path(args[0]).name
            if name in ('termux-x11', 'com.termux.x11'):
                tracked.append(int(path.name))
            if name == 'termux-x11' and display.split('.')[0] in args:
                servers.append(int(path.name))
        except OSError:
            pass
    if requested is not None:
        if requested not in servers:
            raise ValueError('--server-pid does not match requested display')
        return requested, tracked
    if len(servers) != 1:
        raise ValueError(f'expected one X11 server for {display}, found {servers}; use --server-pid')
    return servers[0], tracked


def surface_layer(text, requested=None):
    names = [s.strip().split(' parentId=')[0].removeprefix('RequestedLayerState{')
             for s in text.splitlines() if s.strip()]
    if requested:
        if requested not in names:
            raise ValueError('requested SurfaceFlinger layer missing')
        return requested
    candidates = [s for s in names if 'SurfaceView[com.termux.x11/' in s]
    # Modern SF lists the container, its background and the BLAST buffer layer.
    # Only the latter owns the presentation history; never select a parent.
    buffers = [s for s in candidates if '(BLAST)' in s and 'Background for ' not in s]
    if buffers:
        candidates = buffers
    if len(candidates) != 1:
        raise ValueError(f'expected one Termux:X11 SurfaceView, found {len(candidates)}; use --surface-layer')
    return candidates[0]


def sf_timestamps(samples, begin, end):
    timestamps = set()
    for sample in samples:
        for line in sample.get('raw', '').splitlines()[1:]:
            fields = line.split()
            if len(fields) != 3:
                continue
            try:
                actual = int(fields[1])
            except ValueError:
                continue
            if begin <= actual <= end and actual not in (0, 9223372036854775807):
                timestamps.add(actual)
    return sorted(timestamps)


def device_conditions(root):
    result = {}
    try:
        display = android('dumpsys', 'display', root=root)
        for key, pattern in (('active_mode', r'mActiveModeId=(\d+)'),
                             ('active_render_rate', r'mActiveRenderFrameRate=([\d.]+)'),
                             ('brightness_actual', r'mCachedBrightnessInfo.brightness=([\d.]+)')):
            match = re.search(pattern, display)
            result[key] = match[1] if match else None
        result['brightness_setting'] = android('settings', 'get', 'system', 'screen_brightness', root=root).strip()
        result['screen_awake'] = 'mWakefulness=Awake' in android('dumpsys', 'power', root=root)
    except (OSError, subprocess.SubprocessError, RuntimeError) as error:
        result['error'] = str(error)
    for key, node in (('battery_status', 'status'), ('battery_temp_raw', 'temp')):
        try:
            result[key] = (root / 'sys/class/power_supply/battery' / node).read_text().strip()
        except OSError:
            result[key] = None
    return result


def frozen_state(server, root):
    try:
        groups = Path(f'/proc/{server}/cgroup').read_text().splitlines()
        unified = next(g.split(':', 2)[2] for g in groups if g.startswith('0::'))
        return (root / 'sys/fs/cgroup' / unified.lstrip('/') / 'cgroup.freeze').read_text().strip()
    except (OSError, StopIteration):
        return 'unknown'


def run_case(label, scene, cmd, out, env, seconds, options):
    case = out / label
    case.mkdir()
    root = options.android_root
    conditions_before = device_conditions(root)
    server, tracked = find_server(env['DISPLAY'], options.server_pid)
    cpu_before = {pid: proc_cpu(pid) for pid in tracked}
    freeze_before = frozen_state(server, root)
    sf, errors = [], []
    stop = threading.Event()
    sample_sf = scene == 'moving' or options.trace

    def collect():
        layer = None
        while not stop.is_set():
            anchor = clocks()
            try:
                if layer is None:
                    layer = surface_layer(android('dumpsys', 'SurfaceFlinger', '--list', root=root), options.surface_layer)
                raw = android('dumpsys', 'SurfaceFlinger', '--latency', layer, root=root)
                sf.append(dict(**anchor, layer=layer, raw=raw))
            except (OSError, subprocess.SubprocessError, RuntimeError, ValueError) as error:
                sf.append(dict(**anchor, error=str(error)))
                layer = None
            stop.wait(options.sf_interval)

    worker = threading.Thread(target=collect, daemon=True) if sample_sf else None
    maps, last_cpu, steady_start, steady_end = '', None, None, None
    rc, child = None, None
    before = clocks()
    try:
        with (case / 'client.log').open('w') as log:
            child = subprocess.Popen(cmd + ['--timings', str((case / 'client.csv').resolve())],
                                     env=env, stdout=log, stderr=log, start_new_session=True)
            if worker:
                worker.start()
            deadline = time.monotonic() + seconds + 20
            while child.poll() is None:
                current = proc_cpu(child.pid)
                if current:
                    last_cpu = current
                    if time.monotonic_ns() - before['monotonic_ns'] > 1_500_000_000:
                        if steady_start is None:
                            steady_start = time.monotonic_ns(), current
                        steady_end = time.monotonic_ns(), current
                if '/vulkan.mali.so' not in maps:
                    try:
                        maps = Path(f'/proc/{child.pid}/maps').read_text()
                    except OSError:
                        pass
                if time.monotonic() > deadline:
                    raise TimeoutError('client timeout')
                time.sleep(.25)
            rc = child.returncode
    except (OSError, subprocess.SubprocessError, TimeoutError) as error:
        errors.append(str(error))
    finally:
        if child and child.poll() is None:
            try:
                os.killpg(child.pid, signal.SIGTERM)
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=3)
            except ProcessLookupError:
                pass
        stop.set()
        if worker and worker.ident is not None:
            worker.join(timeout=11)
            if worker.is_alive():
                errors.append('SurfaceFlinger collector did not stop')
    after = clocks()
    freeze_after = frozen_state(server, root)
    tracked_cpu = {}
    for pid, previous in cpu_before.items():
        current = proc_cpu(pid)
        tracked_cpu[str(pid)] = ((current[1] - previous[1]) / os.sysconf('SC_CLK_TCK')
                                 if current and previous and current[0] == previous[0] else None)
    conditions_after = device_conditions(root)
    (case / 'client.maps').write_text(maps)
    (case / 'sf.json').write_text(json.dumps(sf, indent=2) + '\n')
    rows = []
    try:
        with (case / 'client.csv').open() as source:
            rows = list(csv.DictReader(source))
        acquire = percent([float(r['acquire_us']) for r in rows])
        host = percent([float(r['host_frame_us']) for r in rows])
        if any(not math.isfinite(float(r[k])) or float(r[k]) < 0
               for r in rows for k in ('acquire_us', 'host_frame_us')):
            raise ValueError('nonfinite or negative frame duration')
    except (OSError, KeyError, ValueError) as error:
        errors.append('invalid client timings: ' + str(error))
        acquire, host = {}, {}
    timestamps = sf_timestamps(sf, before['monotonic_ns'], after['monotonic_ns'])
    intervals = [(b - a) / 1e6 for a, b in zip(timestamps, timestamps[1:])]
    keys = ('brightness_setting', 'active_mode', 'active_render_rate', 'brightness_actual')
    unchanged = (not conditions_before.get('error') and not conditions_after.get('error')
                 and all(conditions_before.get(k) is not None
                         and conditions_before[k] == conditions_after.get(k) for k in keys))
    offset = ((after['boottime_ns'] - after['monotonic_ns']) - (before['boottime_ns'] - before['monotonic_ns']))
    invalid = errors.copy()
    for failed, reason in (
        (rc != 0, 'client did not exit successfully'), (not rows, 'no client frames'),
        (len(rows) != (seconds * (options.rate or options.fps) if scene == 'moving' else 1),
         'client frame count does not match requested workload'),
        ('/vulkan.mali.so' not in maps, 'Mali runtime mapping unconfirmed'),
        (not unchanged, 'display conditions changed or unavailable'),
        (not all(c.get('screen_awake') for c in (conditions_before, conditions_after)), 'screen not awake'),
        (freeze_before != '0' or freeze_after != '0', 'server freezer state unavailable or frozen'),
        (abs(offset) >= 1_000_000, 'suspend/clock offset changed'),
        (sample_sf and len(timestamps) < 2, 'insufficient SF present samples'),
        (sample_sf and any(s.get('error') for s in sf), 'SF collection incomplete')):
        if failed:
            invalid.append(reason)
    steady_cpu = None
    if steady_start and steady_end and steady_end[0] > steady_start[0]:
        steady_cpu = ((steady_end[1][1] - steady_start[1][1]) * 1e12 / os.sysconf('SC_CLK_TCK')
                      / (steady_end[0] - steady_start[0]))
    return dict(label=label, scene=scene, rc=rc, start=before, end=after, server_pid=server,
                client_pid=child.pid if child else None, conditions_before=conditions_before,
                conditions_after=conditions_after, conditions_unchanged=bool(unchanged),
                freezer_before=freeze_before, freezer_after=freeze_after, clock_offset_change_ns=offset,
                client_frames=len(rows), client_cpu_s=last_cpu[1] / os.sysconf('SC_CLK_TCK') if last_cpu else None,
                client_cpu_method='last live proc stat; final exit ticks may be missed',
                steady_cpu_ms_per_s=steady_cpu, tracked_cpu_s=tracked_cpu,
                mali_mapped='/vulkan.mali.so' in maps, sf_sampling_enabled=sample_sf,
                sf_poll_interval_s=options.sf_interval if sample_sf else None,
                sf_collection_errors=sum(bool(s.get('error')) for s in sf),
                actual_sf_presents=len(timestamps) if sample_sf else None,
                actual_sf_interval_ms=percent(intervals), actual_sf_max_ms=max(intervals) if intervals else None,
                actual_sf_hz=(len(timestamps) - 1) * 1e9 / (timestamps[-1] - timestamps[0]) if len(timestamps) > 1 else None,
                sf_measurement='whole Termux:X11 Surface; unrelated apps may contribute; not unique content FPS',
                acquire_us=acquire, host_frame_us=host, valid=not invalid, invalid_reasons=invalid)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=8)
    parser.add_argument('--width', type=int)
    parser.add_argument('--height', type=int)
    parser.add_argument('--runs', type=int, default=3)
    parser.add_argument('--baseline', type=Path, help='default: current gpu-run prefix')
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument('--candidate', type=Path, help='explicit installed candidate')
    selection.add_argument('--baseline-only', action='store_true')
    parser.add_argument('--scenes', default='moving,static')
    parser.add_argument('--trace', action='store_true')
    parser.add_argument('--rate', type=int, default=0, help='0: Acquire/Present drives producer')
    parser.add_argument('--fps', type=int, default=120)
    parser.add_argument('--android-root', type=Path, default=Path('/proc/1/root'))
    parser.add_argument('--server-pid', type=int)
    parser.add_argument('--surface-layer')
    parser.add_argument('--sf-interval', type=float, default=1.0)
    parser.add_argument('--fullscreen', action='store_true', help='explicitly cover the desktop')
    options = parser.parse_args(argv)
    if not (2 <= options.seconds <= 60 and 1 <= options.runs <= 10 and 0 <= options.rate <= 240
            and 1 <= options.fps <= 240 and .25 <= options.sf_interval <= 2):
        parser.error('invalid duration/runs/rate/fps/SF interval')
    scenes = options.scenes.split(',')
    if any(s not in ('moving', 'static') for s in scenes) or len(set(scenes)) != len(scenes):
        parser.error('scenes must be unique moving/static entries')
    display = os.environ.get('DISPLAY', ':1')
    try:
        runner = shutil.which('gpu-run')
        if options.baseline is None and runner is None:
            raise ValueError('gpu-run unavailable; specify --baseline')
        baseline = release_identity(options.baseline or Path(runner).resolve().parent.parent)
        candidate = release_identity(options.candidate) if options.candidate else None
        size = display_size(display) if options.width is None or options.height is None else (options.width, options.height)
        width = options.width if options.width is not None else size[0]
        height = options.height if options.height is not None else size[1]
        if not (64 <= width <= 10000 and 32 <= height <= 10000):
            raise ValueError('invalid dimensions')
        find_server(display, options.server_pid)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.error(str(error))
    variants = [('baseline-auto', baseline, 'auto')]
    if candidate:
        variants += [('candidate-timer', candidate, 'timer'), ('candidate-auto', candidate, 'auto')]
    options.output.mkdir(exist_ok=False, parents=True)
    client = Path((candidate or baseline)['prefix']) / 'bin/probe-present'
    (options.output / 'metadata.json').write_text(json.dumps(dict(
        baseline=baseline, candidate=candidate, client=str(client),
        probe_sha256=hashlib.sha256(client.read_bytes()).hexdigest(), display=display,
        width=width, height=height, fullscreen=options.fullscreen, android_root=str(options.android_root),
        fps=options.fps, diagnostics_enabled=options.trace), indent=2) + '\n')
    results = []
    for iteration in range(options.runs):
        for variant, identity, policy in (variants if iteration % 2 == 0 else variants[::-1]):
            for scene in scenes:
                label = f'{iteration}-{variant}-{scene}'
                env = dict(os.environ, DISPLAY=display,
                           XDG_RUNTIME_DIR=os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.geteuid()}'),
                           PAD_GPU_MAX_FPS=str(options.fps), PAD_GPU_PRESENT_CLOCK=policy,
                           PAD_GPU_WSI_TRACE='1' if options.trace else '0')
                env.pop('PAD_GPU_WSI_TIMELINE_DIR', None)
                if options.trace:
                    timeline = (options.output / (label + '-timeline')).resolve()
                    timeline.mkdir()
                    env['PAD_GPU_WSI_TIMELINE_DIR'] = str(timeline)
                cmd = [str(Path(identity['prefix']) / 'bin/gpu-run'), 'vulkan', str(client),
                       '--bgra', '--motion', '--cycles', '1', '--width', str(width), '--height', str(height),
                       '--delay-ms', '0', '--rate', str(options.rate), '--frames',
                       str(options.seconds * (options.rate or options.fps) if scene == 'moving' else 1)]
                if options.fullscreen:
                    cmd.append('--fullscreen')
                if scene == 'static':
                    cmd += ['--idle-ms', str(options.seconds * 1000)]
                try:
                    result = run_case(label, scene, cmd, options.output, env, options.seconds, options)
                except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                    result = dict(label=label, scene=scene, valid=False,
                                  invalid_reasons=[str(error)], client_frames=None, actual_sf_hz=None)
                    (options.output / label).mkdir(exist_ok=True)
                result.update(identity=identity, clock_policy=policy, run=iteration,
                              producer_rate=options.rate, trace_enabled=options.trace)
                if options.trace:
                    values = []
                    for path in timeline.glob('*.csv'):
                        with path.open() as source:
                            for event in csv.DictReader(source):
                                if event.get('stage') == 'display_clock_fps':
                                    try:
                                        values.append(int(event['value']))
                                    except (KeyError, ValueError):
                                        pass
                    result['negotiated_clock_fps'] = values
                    if policy == 'auto' and not any(values):
                        result['display_clock_validation_pending'] = True
                results.append(result)
                (options.output / label / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
                (options.output / 'summary.json').write_text(json.dumps(results, indent=2) + '\n')
                print(json.dumps(dict(label=label, valid=result['valid'], invalid_reasons=result['invalid_reasons'],
                                      client_frames=result['client_frames'], sf_hz=result['actual_sf_hz'])), flush=True)
    return 0 if all(result['valid'] for result in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
