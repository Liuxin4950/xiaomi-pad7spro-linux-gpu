#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compare isolated WSI prefixes using the same client, window and frame policy.

Host timing and CPU measurements are not scanout latency or GPU timestamp queries.
The current X11 server and other applications remain running throughout.
"""
import argparse
import csv
import json
import os
from pathlib import Path
import resource
import subprocess
import time


def percentile(values, percent):
    ordered = sorted(values)
    return ordered[int((len(ordered) - 1) * percent / 100)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--r2", type=Path, default=Path("/opt/pad7spro-gpu-dev-20261007-r2"))
    parser.add_argument("--r3", type=Path, default=Path("/opt/pad7spro-gpu-dev-20261012-r3"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=300)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--mailbox", action="store_true")
    parser.add_argument("--trace", action="store_true", help="enable r3 WSI host metrics (adds instrumentation)")
    args = parser.parse_args()
    if not (21 <= args.frames <= 100000 and 1 <= args.runs <= 20 and
            1 <= args.width <= 10000 and 1 <= args.height <= 10000):
        parser.error("invalid workload size or run count")
    args.r2, args.r3 = args.r2.resolve(), args.r3.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    summaries = []
    client = args.r3 / "bin/probe-present"
    variants = [("r2", args.r2, "0"), ("r3-record", args.r3, "0"), ("r3-reuse", args.r3, "1")]
    for run in range(args.runs):
        # Alternate order to reduce systematic warm-up and temperature bias.
        for name, prefix, reuse in (variants if run % 2 == 0 else variants[::-1]):
            label = f"{name}-{run}"
            timings = (args.output / (label + ".csv")).resolve()
            environment = dict(os.environ, DISPLAY=os.environ.get("DISPLAY", ":1"),
                               XDG_RUNTIME_DIR=os.environ.get("XDG_RUNTIME_DIR", "/run/user/0"),
                               PAD_GPU_MAX_FPS="60", PAD_GPU_WSI_REUSE_COMMANDS=reuse,
                               PAD_GPU_WSI_TRACE="1" if args.trace else "0")
            command = [str(prefix / "bin/gpu-run"), "vulkan", str(client), "--bgra",
                       "--cycles", "1", "--frames", str(args.frames), "--delay-ms", "0",
                       "--width", str(args.width), "--height", str(args.height), "--timings", str(timings)]
            if args.mailbox:
                command.append("--mailbox")
            before = resource.getrusage(resource.RUSAGE_CHILDREN)
            started = time.monotonic()
            with (args.output / (label + ".log")).open("xb") as log:
                process = subprocess.Popen(command, env=environment, stdout=log, stderr=log)
                try:
                    deadline = time.monotonic() + 10
                    while True:
                        try:
                            maps = Path(f"/proc/{process.pid}/maps").read_text()
                        except OSError:
                            maps = ""
                        if str(prefix / "lib/libsysvk.so") in maps and "/vendor/lib64/hw/vulkan.mali.so" in maps:
                            break
                        if process.poll() is not None or time.monotonic() >= deadline:
                            raise RuntimeError("expected prefix/Mali driver not mapped")
                        time.sleep(0.05)
                    (args.output / (label + ".maps")).write_text(maps)
                    code = process.wait(timeout=args.frames / 30 + 30)
                finally:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
            if code:
                raise RuntimeError(f"{label} failed: {code}; inspect its log")
            after = resource.getrusage(resource.RUSAGE_CHILDREN)
            rows = list(csv.DictReader(timings.open()))[20:]
            intervals = [(int(b["start_ns"]) - int(a["start_ns"])) / 1e6
                         for a, b in zip(rows, rows[1:])]
            result = dict(variant=name, run=run, width=args.width, height=args.height,
                          mode="mailbox" if args.mailbox else "fifo", frames=args.frames,
                          r3_wsi_trace=args.trace,
                          wall_s=time.monotonic() - started,
                          cpu_s=after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime,
                          voluntary_switches=after.ru_nvcsw-before.ru_nvcsw,
                          involuntary_switches=after.ru_nivcsw-before.ru_nivcsw,
                          host_frame_interval_ms={f"p{p}": percentile(intervals, p) for p in (50, 95, 99)})
            summaries.append(result)
            (args.output / "summary.json").write_text(json.dumps(summaries, indent=2) + "\n")
            print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
