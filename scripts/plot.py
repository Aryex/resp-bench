#!/usr/bin/env python3
"""Plot stability test results: latency, throughput, and heap usage over time."""

import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from hdrh.log import HistogramLogReader


def smooth(data, window=50):
    """Rolling mean for smoothing plot lines. Skips if too few data points."""
    if len(data) < window * 2:
        return np.array(data)
    return np.convolve(data, np.ones(window) / window, mode='same')


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
    parser.add_argument('--heap', type=Path, default=None,
                        help='Results JSON file for JVM heap data')
    parser.add_argument('--gc', type=Path, default=None,
                        help='Results JSON file for GC pause data')
    parser.add_argument('--hlog', type=Path, default=None,
                        help='Path to .hlog file (latency & throughput data)')
    parser.add_argument('-o', '--output', type=Path, required=True,
                        help='Output PNG path')
    args = parser.parse_args()

    if not args.heap and not args.gc and not args.hlog:
        parser.error('at least one of --heap, --gc, or --hlog is required')

    heap, gc, rss = None, None, None
    if args.heap:
        d = json.load(open(args.heap))
        heap_data = d['results']['jvm']['heap']
        if heap_data and heap_data.get('timestamps_epoch'):
            heap = heap_data
        rss_data = d.get('results', {}).get('process', {}).get('smaps', {})
        if rss_data and rss_data.get('rss_kb'):
            rss = rss_data
    if args.gc:
        d = json.load(open(args.gc))
        gc_data = d['results']['jvm']['gc']
        if gc_data and gc_data.get('pauses'):
            gc = gc_data

    series = read_hlog(args.hlog) if args.hlog else {}

    colors = {'GET': '#2196F3', 'SET': '#FF9800'}

    # Build panel list dynamically — only include panels that have data
    panels = []
    if series:
        panels.extend(['throughput', 'latency_p50', 'latency_p99'])
    if heap:
        panels.append('heap')
    if gc:
        panels.append('gc')

    if not panels:
        print('No data to plot')
        sys.exit(0)

    fig, axes = plt.subplots(len(panels), 1, figsize=(14, 4 * len(panels)))
    if len(panels) == 1:
        axes = [axes]
    fig.suptitle('Stability Test Results', fontsize=14, fontweight='bold')

    panel_idx = 0

    # --- Throughput over time ---
    if 'throughput' in panels:
        ax = axes[panel_idx]; panel_idx += 1
        for cmd, s in series.items():
            ax.plot(s['times'], s['throughput'], color=colors.get(cmd, 'gray'),
                    label=cmd, linewidth=0.8)
        ax.set_xlabel('Time (min)')
        ax.set_ylabel('Requests / interval')
        ax.set_title('Throughput')
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

    # --- Latency p50 ---
    if 'latency_p50' in panels:
        ax = axes[panel_idx]; panel_idx += 1
        for cmd, s in series.items():
            ax.plot(s['times'], smooth(s['p50']), color=colors.get(cmd, 'gray'),
                    linewidth=0.8, label=f'{cmd} p50')
        ax.set_xlabel('Time (min)')
        ax.set_ylabel('Latency (µs)')
        ax.set_title('Latency (p50)')
        ax.legend(fontsize=7)
        ax.grid(True, alpha=0.3)

    # --- Latency p99 ---
    if 'latency_p99' in panels:
        ax = axes[panel_idx]; panel_idx += 1
        for cmd, s in series.items():
            ax.plot(s['times'], smooth(s['p99']), color=colors.get(cmd, 'gray'),
                    linewidth=0.8, label=f'{cmd} p99')
        ax.set_xlabel('Time (min)')
        ax.set_ylabel('Latency (µs)')
        ax.set_title('Latency (p99)')
        ax.legend(fontsize=7)
        ax.grid(True, alpha=0.3)

    # --- Heap usage over time ---
    if 'heap' in panels:
        ax = axes[panel_idx]; panel_idx += 1
        t0 = heap['timestamps_epoch'][0]
        ts_min = [(t - t0) / 60 for t in heap['timestamps_epoch']]
        used_mb = [k / 1024 for k in heap['heap_used_kb']]
        total_mb = [k / 1024 for k in heap['heap_total_kb']]
        ax.plot(ts_min, used_mb, 'b-o', markersize=3, label='Heap Used')
        ax.plot(ts_min, total_mb, 'r--', alpha=0.5, label='Heap Total')
        ax.fill_between(ts_min, used_mb, alpha=0.15, color='blue')
        if rss:
            rss_t0 = rss['timestamps_epoch'][0]
            rss_min = [(t - rss_t0) / 60 for t in rss['timestamps_epoch']]
            rss_mb = [k / 1024 for k in rss['rss_kb']]
            anon_mb = [k / 1024 for k in rss['anon_kb']]
            ax.plot(rss_min, rss_mb, 'g-s', markersize=3, label='Process RSS')
            ax.plot(rss_min, anon_mb, 'm-^', markersize=3, label='Anonymous (native)')
            ax.fill_between(rss_min, rss_mb, alpha=0.10, color='green')
            ax.set_title(f'Memory (heap peak: {max(used_mb):.0f} MB, RSS peak: {max(rss_mb):.0f} MB, native peak: {max(anon_mb):.0f} MB)')
        else:
            ax.set_title(f'JVM Heap (peak: {max(used_mb):.0f} MB / {total_mb[0]:.0f} MB)')
        ax.legend(fontsize=8)
        ax.set_xlabel('Time (min)')
        ax.set_ylabel('MB')
        ax.grid(True, alpha=0.3)

    # --- GC pauses over time ---
    if 'gc' in panels:
        ax = axes[panel_idx]; panel_idx += 1
        gc_min = [p['uptime_s'] / 60 for p in gc['pauses']]
        gc_ms = [p['pause_ms'] for p in gc['pauses']]
        ax.stem(gc_min, gc_ms, linefmt='g-', markerfmt='go', basefmt='k-')
        avg_ms = sum(gc_ms) / len(gc_ms)
        ax.axhline(avg_ms, color='orange', linestyle='--', alpha=0.7,
                    label=f'avg: {avg_ms:.1f}ms')
        ax.set_title(f'GC Pauses ({len(gc_ms)} events, max: {max(gc_ms):.1f}ms)')
        ax.legend(fontsize=8)
        ax.set_xlabel('Time (min)')
        ax.set_ylabel('Pause (ms)')
        ax.grid(True, alpha=0.3)
    ax.grid(True, alpha=0.3)

    fig.tight_layout(rect=[0, 0, 1, 0.98])
    fig.savefig(args.output, dpi=150)
    print(f"Saved to {args.output}")


if __name__ == '__main__':
    main()
