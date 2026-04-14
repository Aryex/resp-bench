# Common Commands

## Run benchmark with system monitoring

Console output is automatically saved to `<output-dir>/console.log`.

```bash
python3 scripts/run_with_monitor.py \
    --server localhost:6379 \
    --driver configs/drivers/default/valkey-glide-csharp.json \
    --workload configs/workloads/glide-stability-30s.json \
    --output-dir output/glide-stability-30s
```

## Run in tmux (long-running tests)

```bash
tmux new-session -d -s bench \
    'python3 scripts/run_with_monitor.py \
        --server localhost:6379 \
        --driver configs/drivers/default/valkey-glide-csharp.json \
        --workload configs/workloads/glide-stability-24h.json \
        --output-dir output/glide-csharp-24h'

# Attach to session
tmux attach -t bench

# Detach: Ctrl+B, then D
```

## Plot results

```bash
python3 scripts/plot_intervals.py \
    output/glide-stability-30s/metrics.ndjson.STEADY.interval.ndjson \
    -o output/glide-stability-30s/report.html \
    --title "Valkey GLIDE C# — 30s Stability"
```

## Compare two runs

```bash
python3 scripts/plot_intervals.py \
    output/run-before/metrics.ndjson.STEADY.interval.ndjson \
    output/run-after/metrics.ndjson.STEADY.interval.ndjson \
    --labels "Before,After" \
    -o output/comparison.html
```

## Available workloads

| Workload | Duration | Description |
|----------|----------|-------------|
| `glide-stability-30s.json` | 30s | Quick smoke test |
| `glide-stability-20min.json` | 20min | 80/20 GET/SET mixed |
| `glide-stability-20min-get-only.json` | 20min | GET-only |
| `glide-stability-20min-set-only.json` | 20min | SET-only |
| `glide-stability-2h.json` | 2h | 80/20 GET/SET mixed |
| `glide-stability-24h.json` | 24h | 80/20 GET/SET mixed |

## Output files

```
<output-dir>/
├── console.log                              # Engine stdout/stderr
├── metrics.ndjson                           # Phase summaries
├── metrics.ndjson.STEADY.interval.ndjson    # Per-interval latency + memory
└── system.ndjson                            # System CPU/RSS (1s samples)
```

## Server management

```bash
make server-standalone-start    # Start Valkey on port 6379
make server-stop                # Stop all servers
valkey-cli FLUSHALL             # Clear all data
```

## Rebuild C# engine (after updating Glide client)

```bash
cd ~/resp-bench
make csharp-clean
cd ~/valkey-glide-csharp
cargo clean --manifest-path rust/Cargo.toml
rm -rf sources/Valkey.Glide/bin sources/Valkey.Glide/obj
cd ~/resp-bench
make csharp-build
```
