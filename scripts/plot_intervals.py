#!/usr/bin/env python3
"""Plot throughput and latency over time from interval NDJSON files.

Reads the .interval.ndjson sidecar files produced by the C# (or future)
engines and generates a self-contained HTML file with Plotly.js charts.

Usage:
    python plot_intervals.py /tmp/interval-test/metrics.ndjson.STEADY.interval.ndjson
    python plot_intervals.py /tmp/interval-test/metrics.ndjson.STEADY.interval.ndjson -o report.html
    python plot_intervals.py file1.interval.ndjson file2.interval.ndjson --labels "GLIDE,SE.Redis"
"""

import argparse
import json
import sys
from pathlib import Path


def load_interval_data(path):
    """Load interval NDJSON into per-command time series."""
    series = {}  # cmd -> {times, rps, requests, errors, p50, p95, p99, p999, max}
    memory = {k: [] for k in ["times", "gc_heap_mb", "working_set_mb",
                               "committed_mb", "native_est_mb"]}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            iv = d["interval"]
            dur = iv["duration_s"]
            elapsed = iv["elapsed_s"]
            if dur <= 0:
                continue
            for cmd, m in d.get("metrics", {}).items():
                if cmd not in series:
                    series[cmd] = {k: [] for k in
                                   ["times", "rps", "requests", "errors",
                                    "p50", "p95", "p99", "p999", "max"]}
                s = series[cmd]
                s["times"].append(elapsed)
                s["requests"].append(m["requests"])
                s["errors"].append(m.get("errors", 0))
                s["rps"].append(m["requests"] / dur)
                lat = m.get("latency", {}).get("summary", {})
                for p in ["p50", "p95", "p99", "p999", "max"]:
                    s[p].append(lat.get(p, 0))
            mem = d.get("memory")
            if mem:
                gc_heap = mem.get("gc_heap_bytes", 0)
                ws = mem.get("working_set_bytes", 0)
                memory["times"].append(elapsed)
                memory["gc_heap_mb"].append(round(gc_heap / 1048576, 1))
                memory["working_set_mb"].append(round(ws / 1048576, 1))
                memory["committed_mb"].append(
                    round(mem.get("gc_committed_bytes", 0) / 1048576, 1))
                memory["native_est_mb"].append(
                    round(max(0, ws - gc_heap) / 1048576, 1))
    return series, memory


def generate_html(datasets, memory_datasets, labels, output_path, title):
    """Generate self-contained HTML with Plotly.js charts."""
    colors = {
        "SET": "#FF9800",
        "GET": "#2196F3",
        "PING": "#4CAF50",
    }
    fallback_colors = ["#9C27B0", "#F44336", "#00BCD4", "#795548"]

    def color_for(cmd, idx):
        return colors.get(cmd, fallback_colors[idx % len(fallback_colors)])

    traces_rps = []
    traces_p50 = []
    traces_p99 = []
    traces_errors = []
    traces_memory = []
    has_errors = False
    has_memory = False

    for ds_idx, (series, mem, label) in enumerate(zip(datasets, memory_datasets, labels)):
        prefix = f"{label} — " if len(datasets) > 1 else ""
        dash = "dot" if ds_idx == 1 else ("dash" if ds_idx == 2 else None)
        line_style = f', "dash": "{dash}"' if dash else ""

        for cmd_idx, (cmd, s) in enumerate(sorted(series.items())):
            c = color_for(cmd, cmd_idx)
            name = f"{prefix}{cmd}"

            traces_rps.append(
                f'{{"x": {json.dumps(s["times"])}, "y": {json.dumps([int(r) for r in s["rps"]])}, '
                f'"name": "{name}", "type": "scatter", "line": {{"color": "{c}"{line_style}}}}}'
            )
            traces_p50.append(
                f'{{"x": {json.dumps(s["times"])}, "y": {json.dumps(s["p50"])}, '
                f'"name": "{name}", "type": "scatter", "line": {{"color": "{c}"{line_style}}}}}'
            )
            traces_p99.append(
                f'{{"x": {json.dumps(s["times"])}, "y": {json.dumps(s["p99"])}, '
                f'"name": "{name}", "type": "scatter", "line": {{"color": "{c}"{line_style}}}}}'
            )
            if any(e > 0 for e in s["errors"]):
                has_errors = True
                traces_errors.append(
                    f'{{"x": {json.dumps(s["times"])}, "y": {json.dumps(s["errors"])}, '
                    f'"name": "{name}", "type": "scatter", "line": {{"color": "{c}"{line_style}}}}}'
                )

        if mem["times"]:
            has_memory = True
            traces_memory.append(
                f'{{"x": {json.dumps(mem["times"])}, "y": {json.dumps(mem["gc_heap_mb"])}, '
                f'"name": "{prefix}Heap", "type": "scatter", "line": {{"color": "#4CAF50"{line_style}}}}}'
            )
            traces_memory.append(
                f'{{"x": {json.dumps(mem["times"])}, "y": {json.dumps(mem["native_est_mb"])}, '
                f'"name": "{prefix}RSS minus Heap", "type": "scatter", "line": {{"color": "#9C27B0"{line_style}}}}}'
            )

    panels = [
        ("throughput", "Throughput (requests/sec)", traces_rps),
        ("p50", "Latency p50 (µs)", traces_p50),
        ("p99", "Latency p99 (µs)", traces_p99),
    ]
    if has_errors:
        panels.append(("errors", "Errors per interval", traces_errors))
    if has_memory:
        panels.append(("memory", "Memory (MB)", traces_memory))

    divs = []
    plots = []
    for panel_id, ylabel, traces in panels:
        divs.append(f'<div id="{panel_id}" style="width:100%;height:350px;margin-bottom:10px;"></div>')
        traces_js = ",\n        ".join(traces)
        plots.append(f"""
    Plotly.newPlot('{panel_id}', [
        {traces_js}
    ], {{
        title: '{ylabel}',
        xaxis: {{title: 'Elapsed (seconds)'}},
        yaxis: {{title: '{ylabel}'}},
        legend: {{orientation: 'h', y: -0.2}},
        margin: {{t: 40, b: 60}}
    }}, {{responsive: true}});""")

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<script src="https://cdn.plot.ly/plotly-2.35.0.min.js"></script>
</head>
<body>
<h2>{title}</h2>
{"".join(divs)}
<script>
{"".join(plots)}
</script>
</body>
</html>"""

    Path(output_path).write_text(html)
    print(f"Wrote {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Plot throughput and latency over time from interval NDJSON files"
    )
    parser.add_argument("files", nargs="+", help="Interval NDJSON file(s)")
    parser.add_argument("-o", "--output", default="interval_report.html",
                        help="Output HTML path (default: interval_report.html)")
    parser.add_argument("--labels", default=None,
                        help="Comma-separated labels for each file (default: filenames)")
    parser.add_argument("--title", default="Interval Metrics",
                        help="Report title")
    args = parser.parse_args()

    labels = args.labels.split(",") if args.labels else [Path(f).stem for f in args.files]
    if len(labels) != len(args.files):
        parser.error(f"Got {len(labels)} labels for {len(args.files)} files")

    datasets = []
    memory_datasets = []
    for f in args.files:
        series, memory = load_interval_data(f)
        if not series:
            print(f"Warning: no data in {f}", file=sys.stderr)
            continue
        datasets.append(series)
        memory_datasets.append(memory)

    if not datasets:
        print("No data to plot", file=sys.stderr)
        sys.exit(1)

    generate_html(datasets, memory_datasets, labels, args.output, args.title)


if __name__ == "__main__":
    main()
