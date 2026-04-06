python3 scripts/run_with_monitor.py \
    --server localhost:6379 \
    --driver configs/drivers/example-valkey-glide-csharp-standalone.json \
    --workload configs/workloads/glide-stability-30s.json \
    --output-dir output/glide-stability-30s

python3 scripts/plot_intervals.py \
    output/glide-stability-30s/metrics.ndjson.STEADY.interval.ndjson \
    -o output/glide-stability-30s/report.html \
    --title "Valkey GLIDE C# — 30s Stability"

tmux new-session -d -s bench 'python3 scripts/run_with_monitor.py \
    --server localhost:6379 \
    --driver configs/drivers/example-valkey-glide-csharp-standalone.json \
    --workload configs/workloads/glide-stability-30s.json \
    --output-dir output/glide-stability-30s'