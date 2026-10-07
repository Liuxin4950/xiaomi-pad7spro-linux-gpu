#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Record raw device counters and interval CPU usage without changing GPU settings."""
import argparse
import csv
import os
from pathlib import Path
import sys
import time


def read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return ""


def process(pid):
    try:
        text = Path(f"/proc/{pid}/stat").read_text()
        fields = text.rsplit(")", 1)[1].split()
        # utime/stime are fields 14/15; starttime prevents PID-reuse miscounts.
        return int(fields[19]), int(fields[11]) + int(fields[12])
    except (OSError, ValueError, IndexError):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, action="append", default=[])
    parser.add_argument("--seconds", type=float, default=10)
    parser.add_argument("--interval", type=float, default=0.5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 0 < args.seconds <= 3600 or not 0.1 <= args.interval <= 60 or any(p <= 0 for p in args.pid):
        parser.error("invalid PID, duration or interval")
    pids = sorted(set(args.pid))
    destination = args.output.open("x", newline="") if args.output else sys.stdout
    try:
        columns = ["elapsed_s", "battery_status", "current_now_raw", "voltage_now_raw",
                   "battery_temp_raw", "gpu_cur_freq_hz"] + [f"cpu_percent_pid_{p}" for p in pids]
        writer = csv.DictWriter(destination, fieldnames=columns)
        writer.writeheader()
        previous = {p: process(p) for p in pids}
        start = last = time.monotonic()
        deadline = start + args.seconds
        clock_ticks = os.sysconf("SC_CLK_TCK")
        while last < deadline:
            time.sleep(min(args.interval, max(0, deadline - last)))
            now = time.monotonic()
            row = {"elapsed_s": f"{now-start:.3f}",
                   "battery_status": read("/sys/class/power_supply/battery/status"),
                   "current_now_raw": read("/sys/class/power_supply/battery/current_now"),
                   "voltage_now_raw": read("/sys/class/power_supply/battery/voltage_now"),
                   "battery_temp_raw": read("/sys/class/power_supply/battery/temp"),
                   "gpu_cur_freq_hz": read("/sys/class/devfreq/gpufreq/cur_freq")}
            for pid in pids:
                current, before = process(pid), previous[pid]
                row[f"cpu_percent_pid_{pid}"] = (
                    f"{(current[1]-before[1])/clock_ticks/(now-last)*100:.2f}"
                    if current and before and current[0] == before[0] else "")
                previous[pid] = current
            writer.writerow(row)
            destination.flush()
            last = now
    finally:
        if args.output:
            destination.close()


if __name__ == "__main__":
    main()
