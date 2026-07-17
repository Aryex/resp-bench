#!/usr/bin/env python3
"""Plot unified throughput/latency comparison from .hlog and .interval.ndjson files.

Usage:
    python plot_comparison.py results/1w-stability/java-glide.hlog \
        results/1w-stability/csharp-glide.interval.ndjson \
        results/1w-stability/php-glide.interval.ndjson \
        --labels "Java Glide,C# Glide,PHP Glide" \
        -o results/1w-stability/comparison.html
"""
import argparse
import json
import sys
from pathlib import Path

def load_ndjson(path):
    """Load .interval.ndjson into per-command time series."""
    series = {}
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
                    series[cmd] = {k: [] for k in ["times", "rps", "p50", "p95", "p99", "p999"]}
                s = series[cmd]
                s["times"].append(elapsed / 3600)  # hours
                s["rps"].append(m["requests"] / dur)
                lat = m.get("latency", {}).get("summary", {})
                for p in ["p50", "p95", "p99", "p999"]:
                    s[p].append(lat.get(p, 0))
    return series

def load_hlog(path):
    """Load HdrHistogram .hlog into per-command time series."""
    from hdrh.log import HistogramLogReader
    from io import StringIO

    # Parse raw lines to extract tag, start, duration, and histogram
    series = {}
    with open(path) as f:
        for line in f:
            if line.startswith("#") or line.startswith('"'):
                continue
            line = line.strip()
            if not line:
                continue
            # Format: Tag=CMD,start,duration,max,base64_histogram
            if line.startswith("Tag="):
                parts = line.split(",", 4)
                cmd = parts[0].split("=")[1]
                start = float(parts[1])
                dur = float(parts[2])
                if dur <= 0:
                    continue
                # Decode histogram to get percentiles
                b64 = parts[4]
                try:
                    from hdrh.histogram import HdrHistogram
                    import base64, zlib, struct
                    raw = base64.b64decode(b64)
                    # Use HistogramLogReader on a single-line "file"
                    fake_log = f'"StartTimestamp","Interval_Length","Interval_Max","Interval_Compressed_Histogram"\n{start},{dur},{parts[3]},{b64}\n'
                    reader = HistogramLogReader(StringIO(fake_log), None)
                    h = reader.get_next_interval_histogram()
                    if h is None:
                        continue
                except Exception:
                    continue

                if cmd not in series:
                    series[cmd] = {k: [] for k in ["times", "rps", "p50", "p95", "p99", "p999"]}
                s = series[cmd]
                s["times"].append(start / 3600)  # hours
                s["rps"].append(h.get_total_count() / dur)
                s["p50"].append(h.get_value_at_percentile(50.0) / 1000)  # ns -> us
                s["p95"].append(h.get_value_at_percentile(95.0) / 1000)
                s["p99"].append(h.get_value_at_percentile(99.0) / 1000)
                s["p999"].append(h.get_value_at_percentile(99.9) / 1000)
    return series

def load_file(path):
    if path.endswith(".hlog"):
        return load_hlog(path)
    return load_ndjson(path)

def rolling_avg(data, window):
    if window <= 1:
        return data
    out = []
    for i in range(len(data)):
        start = max(0, i - window + 1)
        out.append(sum(data[start:i+1]) / (i - start + 1))
    return out

def generate_html(datasets, labels, output_path, title, window):
    # Colors per dataset, line style per command
    ds_colors = ["#2196F3", "#FF9800", "#4CAF50", "#9C27B0", "#F44336"]
    cmd_dashes = {"GET": None, "SET": "dash", "PING": "dot"}

    traces_rps = []
    traces_p50 = []
    traces_p99 = []

    for ds_idx, (series, label) in enumerate(zip(datasets, labels)):
        color = ds_colors[ds_idx % len(ds_colors)]
        for cmd, s in sorted(series.items()):
            dash = cmd_dashes.get(cmd, "dot")
            line_style = f', "dash": "{dash}"' if dash else ""
            name = f"{label} {cmd}"
            rps_smooth = rolling_avg(s["rps"], window)
            p50_smooth = rolling_avg(s["p50"], window)
            p99_smooth = rolling_avg(s["p99"], window)

            traces_rps.append(
                f'{{"x": {json.dumps(s["times"])}, "y": {json.dumps([round(r) for r in rps_smooth])}, '
                f'"name": "{name}", "type": "scatter", "line": {{"color": "{color}"{line_style}}}}}'
            )
            traces_p50.append(
                f'{{"x": {json.dumps(s["times"])}, "y": {json.dumps([round(v,1) for v in p50_smooth])}, '
                f'"name": "{name}", "type": "scatter", "line": {{"color": "{color}"{line_style}}}}}'
            )
            traces_p99.append(
                f'{{"x": {json.dumps(s["times"])}, "y": {json.dumps([round(v,1) for v in p99_smooth])}, '
                f'"name": "{name}", "type": "scatter", "line": {{"color": "{color}"{line_style}}}}}'
            )

    panels = [
        ("throughput", "Throughput (req/s)", traces_rps, "0"),
        ("p50", "Latency p50 (µs)", traces_p50, "0"),
        ("p99", "Latency p99 (µs)", traces_p99, "0"),
    ]

    divs = []
    plots = []
    for panel_id, ylabel, traces, rangemode in panels:
        divs.append(f'<div id="{panel_id}" style="width:100%;height:400px;margin-bottom:20px;"></div>')
        traces_js = ",\n        ".join(traces)
        plots.append(f"""
    Plotly.newPlot('{panel_id}', [
        {traces_js}
    ], {{
        title: '{ylabel}',
        xaxis: {{title: 'Elapsed (hours)'}},
        yaxis: {{title: '{ylabel}', rangemode: 'tozero'}},
        legend: {{orientation: 'h', y: -0.15}},
        margin: {{t: 40, b: 80}}
    }}, {{responsive: true}});""")

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{title}</title>
<script src="https://cdn.plot.ly/plotly-2.35.0.min.js"></script>
</head><body>
<h2>{title}</h2>
<p style="color:#666">Rolling average window: {window} intervals ({window*30}s). Line style: solid=GET, dashed=SET, dotted=PING</p>
{"".join(divs)}
<script>{"".join(plots)}</script>
</body></html>"""
    Path(output_path).write_text(html)
    print(f"Wrote {output_path}")

def main():
    parser = argparse.ArgumentParser(description="Unified comparison plot for .hlog and .interval.ndjson")
    parser.add_argument("files", nargs="+")
    parser.add_argument("-o", "--output", default="comparison.html")
    parser.add_argument("--labels", default=None)
    parser.add_argument("--title", default="1-Week Stability Comparison: Java vs C# vs PHP (Valkey Glide)")
    parser.add_argument("--window", type=int, default=30, help="Rolling average window (intervals)")
    args = parser.parse_args()

    labels = args.labels.split(",") if args.labels else [Path(f).stem for f in args.files]
    datasets = []
    for f in args.files:
        series = load_file(f)
        if not series:
            print(f"Warning: no data in {f}", file=sys.stderr)
            continue
        datasets.append(series)
    if not datasets:
        sys.exit("No data to plot")
    generate_html(datasets, labels, args.output, args.title, args.window)

if __name__ == "__main__":
    main()
