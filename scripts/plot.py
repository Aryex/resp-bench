#!/usr/bin/env python3
"""Plot stability test results: latency, throughput, and heap usage over time."""

import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from hdrh.log import HistogramLogReader


def read_hlog(hlog_path):
    """Read .hlog into per-command time-series."""
    series = {}  # cmd -> {times, throughput, p50, p99, p999, max}
    reader = HistogramLogReader(str(hlog_path), None)
    t0 = None
    h = reader.get_next_interval_histogram()
    while h is not None:
        tag = h.get_tag() or "UNKNOWN"
        ts = h.get_start_time_stamp() / 1000  # epoch seconds
        if t0 is None:
            t0 = ts
        if tag not in series:
            series[tag] = {'times': [], 'throughput': [], 'p50': [], 'p99': [], 'p999': [], 'max': []}
        s = series[tag]
        s['times'].append((ts - t0) / 60)  # minutes
        s['throughput'].append(h.get_total_count())
        s['p50'].append(h.get_value_at_percentile(50))
        s['p99'].append(h.get_value_at_percentile(99))
        s['p999'].append(h.get_value_at_percentile(99.9))
        s['max'].append(h.get_max_value())
        h = reader.get_next_interval_histogram()
    return series


def main():
    parser = argparse.ArgumentParser(description='Plot stability test results')
    parser.add_argument('input', type=Path, help='Results JSON file')
    parser.add_argument('-o', '--output', type=Path, default=None,
                        help='Output PNG (default: <input>_plots.png)')
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: {args.input} not found", file=sys.stderr)
        sys.exit(1)

    output = args.output or args.input.with_name(args.input.stem + '_plots.png')

    d = json.load(open(args.input))
    results = d['results']
    heap = results['jvm']['heap']
    gc = results['jvm']['gc']

    # Find hlog file
    hlog_files = list(args.input.parent.glob("*.hlog"))
    if not hlog_files:
        print("Error: no .hlog file found in output dir", file=sys.stderr)
        sys.exit(1)
    series = read_hlog(hlog_files[0])

    colors = {'GET': '#2196F3', 'SET': '#FF9800'}

    fig, axes = plt.subplots(2, 2, figsize=(14, 8))
    fig.suptitle('Stability Test Results', fontsize=14, fontweight='bold')

    # --- Throughput over time (top-left) ---
    ax = axes[0][0]
    for cmd, s in series.items():
        ax.plot(s['times'], s['throughput'], color=colors.get(cmd, 'gray'),
                label=cmd, linewidth=0.8)
    ax.set_xlabel('Time (min)')
    ax.set_ylabel('Requests / interval')
    ax.set_title('Throughput')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # --- Latency p50/p99 over time (top-right) ---
    ax = axes[0][1]
    for cmd, s in series.items():
        c = colors.get(cmd, 'gray')
        ax.plot(s['times'], s['p50'], color=c, linewidth=0.8,
                label=f'{cmd} p50')
        ax.plot(s['times'], s['p99'], color=c, linewidth=0.8,
                linestyle='--', alpha=0.7, label=f'{cmd} p99')
    ax.set_xlabel('Time (min)')
    ax.set_ylabel('Latency (µs)')
    ax.set_title('Latency (p50 / p99)')
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.3)

    # --- Heap usage over time (bottom-left) ---
    ax = axes[1][0]
    t0 = heap['timestamps_epoch'][0]
    ts_min = [(t - t0) / 60 for t in heap['timestamps_epoch']]
    used_mb = [k / 1024 for k in heap['heap_used_kb']]
    total_mb = [k / 1024 for k in heap['heap_total_kb']]
    ax.plot(ts_min, used_mb, 'b-o', markersize=3, label='Heap Used')
    ax.plot(ts_min, total_mb, 'r--', alpha=0.5, label='Heap Total')
    ax.fill_between(ts_min, used_mb, alpha=0.15, color='blue')
    ax.set_xlabel('Time (min)')
    ax.set_ylabel('MB')
    ax.set_title(f'JVM Heap (peak: {max(used_mb):.0f} MB / {total_mb[0]:.0f} MB)')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # --- GC pauses over time (bottom-right) ---
    ax = axes[1][1]
    if gc.get('pauses'):
        gc_min = [p['uptime_s'] / 60 for p in gc['pauses']]
        gc_ms = [p['pause_ms'] for p in gc['pauses']]
        ax.stem(gc_min, gc_ms, linefmt='g-', markerfmt='go', basefmt='k-')
        avg_ms = sum(gc_ms) / len(gc_ms)
        ax.axhline(avg_ms, color='orange', linestyle='--', alpha=0.7,
                    label=f'avg: {avg_ms:.1f}ms')
        ax.set_title(f'GC Pauses ({len(gc_ms)} events, max: {max(gc_ms):.1f}ms)')
        ax.legend(fontsize=8)
    else:
        ax.text(0.5, 0.5, 'No GC data', ha='center', va='center',
                transform=ax.transAxes)
        ax.set_title('GC Pauses')
    ax.set_xlabel('Time (min)')
    ax.set_ylabel('Pause (ms)')
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(output, dpi=150)
    print(f"Saved to {output}")


if __name__ == '__main__':
    main()
