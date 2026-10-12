#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read process CPU and same-PID ExceptionUploader events on one clock timeline.

Runs in Debian or native Termux Python. It never changes services or settings.
"""
import argparse
import csv
from collections import deque
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time


def read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return ""


def stat(pid, tid=None):
    path = f"/proc/{pid}/stat" if tid is None else f"/proc/{pid}/task/{tid}/stat"
    try:
        fields = Path(path).read_text().rsplit(")", 1)[1].split()
        return int(fields[19]), int(fields[11]) + int(fields[12])
    except (OSError, ValueError, IndexError):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, action="append", default=[])
    parser.add_argument("--daemon-pid", type=int, required=True)
    parser.add_argument("--seconds", type=float, default=30)
    parser.add_argument("--interval", type=float, default=1)
    parser.add_argument("--android-root", type=Path, default=Path("/proc/1/root"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--label", default="unspecified")
    args = parser.parse_args()
    if not (0 < args.seconds <= 3600 and 0.2 <= args.interval <= 10 and args.daemon_pid > 0):
        parser.error("invalid duration, interval or PID")
    pids = sorted(set(args.pid + [args.daemon_pid]))
    if any(p <= 0 for p in pids):
        parser.error("invalid PID")
    args.output.mkdir(parents=True, exist_ok=False)
    args.output.chmod(0o700)
    hot_threads = {}
    for path in Path(f"/proc/{args.daemon_pid}/task").iterdir():
        name = read(path / "comm")
        if name in ("CoreEventUpload", "HeapTaskDaemon"):
            hot_threads[name] = int(path.name)
    metadata = dict(label=args.label, boot_id=read("/proc/sys/kernel/random/boot_id"),
                    clock_ticks=os.sysconf("SC_CLK_TCK"), pids=pids, daemon_pid=args.daemon_pid,
                    hot_threads=hot_threads, pid_start_ticks={p: stat(p)[0] if stat(p) else None for p in pids},
                    process_context={p: dict(cgroup=read(f"/proc/{p}/cgroup"),
                                            comm=read(f"/proc/{p}/comm")) for p in pids})
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    command = ["/system/bin/logcat", "-v", "epoch,usec", "-T", "1", f"--pid={args.daemon_pid}", "-s", "ExceptionUploader:E"]
    if str(args.android_root) != "/":
        command = ["/usr/sbin/chroot", str(args.android_root), *command]
    logs = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    events, lock = deque(), threading.Lock()
    pattern = re.compile(r"^\s*(\d+)\.(\d+)\s+(\d+)\s+(\d+)\s+E\s+ExceptionUploader\s*:.*String.contains")
    def collect():
        with (args.output / "exceptions.jsonl").open("x") as file:
            for line in logs.stdout:
                match = pattern.search(line)
                if not match or int(match[3]) != args.daemon_pid:
                    continue
                epoch_ns = int(match[1])*10**9 + int(match[2].ljust(9, "0")[:9])
                event = dict(realtime_ns=epoch_ns, pid=int(match[3]), tid=int(match[4]),
                             reader_monotonic_ns=time.monotonic_ns(), reader_boottime_ns=time.clock_gettime_ns(7))
                file.write(json.dumps(event) + "\n")
                with lock:
                    events.append(event)
    worker = threading.Thread(target=collect)
    worker.start()
    columns = ["elapsed_s", "monotonic_ns", "boottime_ns", "realtime_ns", "exception_count", "late_logs",
               "system_cpu_ms", "system_cpu_busy_pct", "current_now_raw", "voltage_now_raw", "temp_raw", "battery_status", "gpu_freq_hz"]
    columns += [f"cpu_ms_pid_{p}" for p in pids]
    columns += [f"cpu_ms_thread_{t}" for t in hot_threads]
    previous = {p: stat(p) for p in pids}
    previous_threads = {n: stat(args.daemon_pid, t) for n, t in hot_threads.items()}
    previous_system = list(map(int, read("/proc/stat").splitlines()[0].split()[1:9]))
    start = last = time.monotonic_ns()
    last_real = time.time_ns()
    try:
        with (args.output / "samples.csv").open("x", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=columns)
            writer.writeheader()
            while (last-start)/1e9 < args.seconds:
                target = min(start + int(args.seconds*1e9), last + int(args.interval*1e9))
                time.sleep(max(0, target-time.monotonic_ns())/1e9)
                now, boot, real = time.monotonic_ns(), time.clock_gettime_ns(7), time.time_ns()
                count = late = 0
                with lock:
                    while events and events[0]["realtime_ns"] <= real:
                        event = events.popleft()
                        if event["realtime_ns"] > last_real:
                            count += 1
                        else:
                            late += 1
                system = list(map(int, read("/proc/stat").splitlines()[0].split()[1:9]))
                delta = [a-b for a, b in zip(system, previous_system)]
                busy = sum(delta) - delta[3] - delta[4]
                row = dict(elapsed_s=f"{(now-start)/1e9:.6f}", monotonic_ns=now, boottime_ns=boot,
                           realtime_ns=real, exception_count=count, late_logs=late,
                           system_cpu_ms=busy*1000/metadata["clock_ticks"],
                           system_cpu_busy_pct=100*busy/sum(delta) if sum(delta) else "",
                           current_now_raw=read("/sys/class/power_supply/battery/current_now"),
                           voltage_now_raw=read("/sys/class/power_supply/battery/voltage_now"),
                           temp_raw=read("/sys/class/power_supply/battery/temp"),
                           battery_status=read("/sys/class/power_supply/battery/status"),
                           gpu_freq_hz=read("/sys/class/devfreq/gpufreq/cur_freq"))
                for pid in pids:
                    current, before = stat(pid), previous[pid]
                    row[f"cpu_ms_pid_{pid}"] = ((current[1]-before[1])*1000/metadata["clock_ticks"]
                        if current and before and current[0] == before[0] else "")
                    previous[pid] = current
                for name, tid in hot_threads.items():
                    current, before = stat(args.daemon_pid, tid), previous_threads[name]
                    row[f"cpu_ms_thread_{name}"] = ((current[1]-before[1])*1000/metadata["clock_ticks"]
                        if current and before and current[0] == before[0] else "")
                    previous_threads[name] = current
                writer.writerow(row)
                file.flush()
                last, last_real, previous_system = now, real, system
    finally:
        logs.terminate()
        try:
            logs.wait(timeout=3)
        except subprocess.TimeoutExpired:
            logs.kill()
            logs.wait()
        worker.join(timeout=3)
        (args.output / "logcat-stderr.txt").write_text(logs.stderr.read())
        metadata.update(end_monotonic_ns=time.monotonic_ns(), end_boottime_ns=time.clock_gettime_ns(7),
                        end_realtime_ns=time.time_ns(), logcat_reader_finished=not worker.is_alive())
        (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")


if __name__ == "__main__":
    main()
