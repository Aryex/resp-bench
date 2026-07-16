#!/usr/bin/env python3
"""
generate_memory_report.py — Generates a self-contained HTML memory report from .memory.ndjson files.

Reads memory samples produced by resp-bench's Ruby engine and creates an interactive
Plotly chart showing:
  - Process RSS (total memory including native/FFI allocations) over time
  - Ruby heap live slots over time (Ruby-managed object count)

Properly handles multiple phases, connection counts, and forked workers by:
  - Separating phases (WARMUP vs STEADY) into distinct chart panels
  - Averaging samples from multiple workers (PIDs) at the same time point
  - Showing one trace per (driver, connection_count) combination

Usage:
    python scripts/generate_memory_report.py results/my-run/ --output memory_report.html
    python scripts/generate_memory_report.py results/my-run/ --output memory_report.html --title "My Run"
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


def load_memory_samples(results_dir: Path) -> list:
    """Load all .memory.ndjson files from a results directory.

    Returns a flat list of all sample dicts (each has driver_id, phase, pid, etc.)
    """
    all_samples = []
    for f in sorted(results_dir.glob("*.memory.ndjson")):
        with open(f) as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        all_samples.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    return all_samples


def group_samples(samples: list) -> dict:
    """Group samples by (driver_id, phase, connections).

    For each group, average the RSS and heap values across multiple workers
    at the same time bucket (rounded to nearest 0.25s).

    Returns: {(driver, phase, conns): [(t, rss_mb, heap_live, malloc_kb), ...]}
    """
    # First, group by (driver, phase, connections, time_bucket)
    raw = defaultdict(lambda: defaultdict(list))

    for s in samples:
        key = (s["driver_id"], s["phase"], s["connections"])
        t_bucket = round(s["t"] * 4) / 4  # round to 0.25s
        raw[key][t_bucket].append(s)

    # Average across workers at each time bucket
    result = {}
    for key, time_buckets in raw.items():
        points = []
        for t, worker_samples in sorted(time_buckets.items()):
            n = len(worker_samples)
            avg_rss = sum(s.get("rss_kb", 0) for s in worker_samples) / n / 1024.0
            avg_heap = sum(s.get("ruby_heap_live_slots", 0) for s in worker_samples) / n
            avg_malloc = sum(s.get("ruby_malloc_increase_bytes", 0) for s in worker_samples) / n / 1024.0
            points.append((t, avg_rss, avg_heap, avg_malloc))
        result[key] = points

    return result


def generate_html(grouped: dict, title: str) -> str:
    """Generate a self-contained HTML file with Plotly charts."""

    # Determine unique phases
    phases = sorted(set(k[1] for k in grouped.keys()),
                    key=lambda p: 0 if p == "WARMUP" else 1)

    colors_by_driver = {}
    palette = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"]
    driver_idx = 0

    def get_color(driver):
        nonlocal driver_idx
        if driver not in colors_by_driver:
            colors_by_driver[driver] = palette[driver_idx % len(palette)]
            driver_idx += 1
        return colors_by_driver[driver]

    # Build chart data per phase
    phase_charts = {}
    for phase in phases:
        rss_traces = []
        heap_traces = []

        for (driver, p, conns), points in sorted(grouped.items()):
            if p != phase:
                continue
            color = get_color(driver)
            # Use dashed line for connections > 1 to distinguish
            dash = "solid" if conns == 1 else "dash"
            trace_label = f"{driver} ({conns} conn)"

            times = [pt[0] for pt in points]
            rss_mb = [pt[1] for pt in points]
            heap_live = [pt[2] for pt in points]

            rss_traces.append({
                "x": times, "y": rss_mb,
                "name": trace_label, "type": "scatter", "mode": "lines",
                "line": {"color": color, "width": 2, "dash": dash},
            })
            heap_traces.append({
                "x": times, "y": heap_live,
                "name": trace_label, "type": "scatter", "mode": "lines",
                "line": {"color": color, "width": 2, "dash": dash},
            })

        phase_charts[phase] = {"rss": rss_traces, "heap": heap_traces}

    # Build summary table
    summary_rows = []
    for (driver, phase, conns), points in sorted(grouped.items()):
        if not points:
            continue
        rss_start = points[0][1]
        rss_end = points[-1][1]
        rss_peak = max(pt[1] for pt in points)
        rss_growth_pct = ((rss_end - rss_start) / rss_start * 100) if rss_start > 0 else 0
        heap_start = points[0][2]
        heap_end = points[-1][2]
        heap_growth_pct = ((heap_end - heap_start) / heap_start * 100) if heap_start > 0 else 0
        duration = points[-1][0]

        summary_rows.append({
            "driver": driver, "phase": phase, "conns": conns,
            "duration": duration,
            "rss_start": rss_start, "rss_end": rss_end, "rss_peak": rss_peak,
            "rss_growth_pct": rss_growth_pct,
            "heap_start": int(heap_start), "heap_end": int(heap_end),
            "heap_growth_pct": heap_growth_pct,
        })

    # Generate HTML
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{title}</title>
    <script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 20px; background: #fafafa; }}
        h1 {{ margin-bottom: 5px; }}
        h2 {{ margin-top: 30px; color: #333; }}
        .subtitle {{ color: #666; margin-bottom: 20px; font-size: 14px; }}
        .chart-container {{ background: white; border-radius: 8px; padding: 15px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .summary {{ background: white; border-radius: 8px; padding: 15px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #eee; }}
        th {{ background: #f5f5f5; font-weight: 600; }}
        .increase {{ color: #d62728; font-weight: 600; }}
        .stable {{ color: #2ca02c; }}
        .note {{ font-size: 12px; color: #888; margin-top: 5px; }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    <p class="subtitle">Process RSS = total memory (Ruby heap + native/FFI). Ruby Heap Slots = GC-managed objects only.<br>
    Solid lines = 1 connection. Dashed lines = 2 connections. Multiple workers are averaged.</p>

    <div class="summary">
        <h3>Summary</h3>
        <table>
            <tr><th>Driver</th><th>Phase</th><th>Conns</th><th>Duration</th><th>RSS Start</th><th>RSS Peak</th><th>RSS End</th><th>RSS Growth</th><th>Heap Start</th><th>Heap End</th><th>Heap Growth</th></tr>
"""

    for row in summary_rows:
        rss_class = "increase" if row["rss_growth_pct"] > 5 else "stable"
        heap_class = "increase" if row["heap_growth_pct"] > 5 else "stable"
        html += f"""            <tr>
                <td><strong>{row["driver"]}</strong></td>
                <td>{row["phase"]}</td>
                <td>{row["conns"]}</td>
                <td>{row["duration"]:.1f}s</td>
                <td>{row["rss_start"]:.1f} MB</td>
                <td>{row["rss_peak"]:.1f} MB</td>
                <td>{row["rss_end"]:.1f} MB</td>
                <td class="{rss_class}">{row["rss_growth_pct"]:+.1f}%</td>
                <td>{row["heap_start"]:,}</td>
                <td>{row["heap_end"]:,}</td>
                <td class="{heap_class}">{row["heap_growth_pct"]:+.1f}%</td>
            </tr>
"""

    html += """        </table>
        <p class="note">Growth% = (end - start) / start × 100. Negative growth is normal for forked workers (COW pages reclaimed).</p>
    </div>
"""

    # Add charts per phase
    chart_idx = 0
    for phase in phases:
        if phase not in phase_charts:
            continue
        rss_json = json.dumps(phase_charts[phase]["rss"])
        heap_json = json.dumps(phase_charts[phase]["heap"])

        html += f"""
    <h2>{phase} Phase</h2>
    <div class="chart-container">
        <div id="rss-chart-{chart_idx}" style="height: 400px;"></div>
    </div>
    <div class="chart-container">
        <div id="heap-chart-{chart_idx}" style="height: 350px;"></div>
    </div>

    <script>
        Plotly.newPlot('rss-chart-{chart_idx}', {rss_json}, {{
            title: '{phase} — Process RSS (Total Memory)',
            xaxis: {{ title: 'Time (seconds)' }},
            yaxis: {{ title: 'RSS (MB)' }},
            legend: {{ orientation: 'h', y: -0.2 }},
            hovermode: 'x unified'
        }}, {{ responsive: true }});

        Plotly.newPlot('heap-chart-{chart_idx}', {heap_json}, {{
            title: '{phase} — Ruby Heap Live Slots',
            xaxis: {{ title: 'Time (seconds)' }},
            yaxis: {{ title: 'Live Slots' }},
            legend: {{ orientation: 'h', y: -0.2 }},
            hovermode: 'x unified'
        }}, {{ responsive: true }});
    </script>
"""
        chart_idx += 1

    html += """
</body>
</html>"""

    return html


def main():
    parser = argparse.ArgumentParser(
        description="Generate HTML memory growth report from .memory.ndjson files"
    )
    parser.add_argument("results_dir", help="Directory containing .memory.ndjson files")
    parser.add_argument("--output", "-o", default="memory_report.html",
                        help="Output HTML file path (default: memory_report.html)")
    parser.add_argument("--title", "-t", default="Memory Growth Report",
                        help="Report title")

    args = parser.parse_args()
    results_dir = Path(args.results_dir)

    if not results_dir.is_dir():
        print(f"Error: {results_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    samples = load_memory_samples(results_dir)
    if not samples:
        print(f"Error: No .memory.ndjson files found in {results_dir}", file=sys.stderr)
        sys.exit(1)

    grouped = group_samples(samples)
    drivers = set(k[0] for k in grouped.keys())
    print(f"Loaded {len(samples)} samples for {len(drivers)} drivers: {', '.join(sorted(drivers))}")
    for key, pts in sorted(grouped.items()):
        print(f"  {key[0]} / {key[1]} / {key[2]} conn: {len(pts)} points, {pts[-1][0]:.1f}s")

    html = generate_html(grouped, args.title)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html)
    print(f"\nReport written to: {output_path}")


if __name__ == "__main__":
    main()
