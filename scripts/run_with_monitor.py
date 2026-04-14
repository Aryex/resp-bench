#!/usr/bin/env python3
"""Run a single benchmark with system monitoring (CPU%, RSS).

Wraps the C# (or any) engine subprocess with system_monitor.py to collect
external system metrics alongside the engine's internal interval metrics.

Usage:
    python run_with_monitor.py \
        --server localhost:6379 \
        --driver configs/drivers/example-valkey-glide-csharp-standalone.json \
        --workload csharp/test-5min-stability.json \
        --output-dir /tmp/stability-test

Produces:
    /tmp/stability-test/metrics.ndjson                          # phase summaries
    /tmp/stability-test/metrics.ndjson.STEADY.interval.ndjson   # internal intervals
    /tmp/stability-test/system.ndjson                           # external CPU/RSS
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# Add scripts dir to path for system_monitor import
sys.path.insert(0, str(Path(__file__).parent))
from system_monitor import SystemMonitor


def detect_engine(driver_path):
    """Auto-detect engine from driver config."""
    with open(driver_path) as f:
        config = json.load(f)
    driver_id = config.get("driver_id", "")
    if driver_id in ("stackexchange-redis", "valkey-glide-csharp", "recording"):
        return "csharp"
    if driver_id in ("redis-rb", "valkey-glide-ruby"):
        return "ruby"
    return "java"


def main():
    parser = argparse.ArgumentParser(description="Run benchmark with system monitoring")
    parser.add_argument("--server", required=True, help="Server endpoint (host:port)")
    parser.add_argument("--driver", required=True, help="Driver config JSON path")
    parser.add_argument("--workload", required=True, help="Workload config JSON path")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--monitor-interval", type=float, default=1.0,
                        help="System monitor sampling interval in seconds (default: 1.0)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    metrics_path = str(output_dir / "metrics.ndjson")
    system_path = str(output_dir / "system.ndjson")

    engine = detect_engine(args.driver)
    bench_cmd = [
        "make", f"{engine}-run",
        f"SERVER={args.server}",
        f"DRIVER={args.driver}",
        f"WORKLOAD={args.workload}",
        f"METRICS_OUTPUT={metrics_path}",
    ]

    log_path = str(output_dir / "console.log")

    print(f"Engine: {engine}")
    print(f"Command: {' '.join(bench_cmd)}")
    print(f"System monitor: {system_path} (interval={args.monitor_interval}s)")
    print(f"Console log: {log_path}")
    print()

    log_file = open(log_path, "w")
    bench_proc = subprocess.Popen(bench_cmd, stdout=log_file, stderr=subprocess.STDOUT,
                                  start_new_session=True)
    pgid = os.getpgid(bench_proc.pid)

    with SystemMonitor(system_path, interval=args.monitor_interval, target_pgid=pgid):
        bench_proc.wait()

    log_file.close()

    # Copy Valkey server log if available
    import shutil
    repo_root = Path(__file__).parent.parent
    valkey_log = repo_root / "work" / "valkey-6379.log"
    if valkey_log.exists():
        shutil.copy2(valkey_log, output_dir / "valkey-server.log")

    if bench_proc.returncode != 0:
        print(f"Benchmark exited with code {bench_proc.returncode}", file=sys.stderr)
        sys.exit(bench_proc.returncode)

    print(f"\nResults in {output_dir}/")
    for f in sorted(output_dir.iterdir()):
        print(f"  {f.name} ({f.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
