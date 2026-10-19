"""Measure a launched Linux app and all its helpers without reading command lines."""

import argparse
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time


def sample(root):
    identifiers, pending = {root}, [root]
    while pending:
        pid = pending.pop()
        try:
            children = {int(value) for task in Path(f"/proc/{pid}/task").glob("*/children") for value in task.read_text().split()}
        except OSError:
            children = set()
        children -= identifiers
        identifiers.update(children)
        pending.extend(children)
    pss, ticks, counted = 0, 0, 0
    for pid in identifiers:
        try:
            memory = Path(f"/proc/{pid}/smaps_rollup").read_text()
            fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
            pss += sum(int(line.split()[1]) for line in memory.splitlines() if line.startswith("Pss:"))
            # Reaped-child time keeps totals continuous when helper processes hibernate.
            ticks += sum(map(int, fields[11:15]))
            counted += 1
        except (OSError, ValueError):
            pass
    return {"processes": counted, "pss_mib": round(pss / 1024, 3), "cpu_ticks": ticks}


def summarize(samples, hz):
    steady = [row for row in samples if row["seconds"] >= max(0, samples[-1]["seconds"] - 60)]
    first, last = steady[0], steady[-1]
    elapsed = last["seconds"] - first["seconds"]
    return {"steady_pss_mib": round(statistics.median(row["pss_mib"] for row in steady), 3), "steady_cpu_one_core_percent": round((last["cpu_ticks"] - first["cpu_ticks"]) / hz / elapsed * 100, 3) if elapsed else None, "measurement_seconds": round(samples[-1]["seconds"], 3)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=1800)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if sys.platform != "linux" or not command or args.seconds < 1:
        parser.error("Use Linux, a positive duration and a command after --")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Child output may contain private artwork URLs; retain it locally, never echo it.
    log = args.output.with_suffix(".private.log")
    fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    samples = []
    with os.fdopen(fd, "w") as handle:
        process = subprocess.Popen(command, stdout=handle, stderr=handle)
        started = time.monotonic()
        try:
            while process.poll() is None and time.monotonic() - started <= args.seconds:
                samples.append({"seconds": round(time.monotonic() - started, 3), **sample(process.pid)})
                args.output.write_text(json.dumps({"status": "running", "samples": samples}, indent=2))
                time.sleep(5)
            process.wait(timeout=45)
        except (KeyboardInterrupt, subprocess.TimeoutExpired):
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            raise
    report = {"status": "passed" if process.returncode == 0 else "failed", "exit_code": process.returncode, "samples": samples, **summarize(samples, os.sysconf("SC_CLK_TCK"))}
    args.output.write_text(json.dumps(report, indent=2))
    print(json.dumps({key: value for key, value in report.items() if key != "samples"}))
    return process.returncode


if __name__ == "__main__":
    raise SystemExit(main())
