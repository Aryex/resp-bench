# resp-bench Benchmark Notes

## Repository
- **Repo**: git@github.com:Aryex/resp-bench.git
- **Upstream**: https://github.com/ikolomi/resp-bench.git

## Branches
- `main` — base repo (Java + Ruby engines)
- `java-bench` — Java engine with valkey-glide, Glide debug logging enabled (writes to glide-debug.log)
- `csharp-bench` — C# engine with Valkey.Glide NuGet package, has interval NDJSON output + plot_intervals.py
- `php-bench` — PHP engine (from prateek-kumar-improving/resp-bench fork), uses valkey-glide-php extension

## EC2 Instances (c5.2xlarge, us-east-1, key: lehminh.pem)
| Name | IP | Instance ID | Branch | Driver | Version |
|------|-----|-------------|--------|--------|---------|
| resp-bench-java | 44.192.82.215 | i-0288fd22159e695ff | java-bench | valkey-glide | 2.4.0-rc3 |
| resp-bench-csharp | 3.235.62.223 | i-01adff4a1cd8e4a77 | csharp-bench | Valkey.Glide (NuGet) | 1.1.0-rc1 |
| resp-bench-php | 44.222.194.250 | i-04f38a39c08cde35d | php-bench | valkey-glide-php (ext) | 1.1.0-rc1 |

## SSH Access
```bash
ssh -i ~/.ssh/lehminh.pem ubuntu@<IP>
```

## Currently Running (started 2026-05-07 ~16:06 UTC)
All 3 instances are running 1-week stability tests WITH monitoring in tmux session `bench`:
- **Java**: `python3 scripts/benchmark_orchestrator.py` — full monitoring (heap, smaps, mpstat, iostat, sar, perf_stat, async-profiler). Output in /dev/shm/ (RAM disk), collected at end.
- **C#**: `python3 scripts/run_with_monitor.py` → output/csharp-1w-rc1-monitored/ (has system.ndjson)
- **PHP**: `python3 scripts/run_with_monitor.py` → output/php-1w-rc1-monitored/ (has system.ndjson)

Check status:
```bash
ssh -i ~/.ssh/lehminh.pem ubuntu@<IP> "tmux capture-pane -t bench -p | tail -5"
```

## Workload Config (identical across all 3)
- Duration: 1 week (604,800s)
- Connections: 10
- Commands: 80% GET / 20% SET, 512B values
- Keyspace: 1M keys, uniform random access, prefix `stability:`
- Interval histograms: every 30s
- Warmup: 1M sequential SETs

## Output Formats
| Engine | Interval Data | Memory Data |
|--------|--------------|-------------|
| Java | `.hlog` (HdrHistogram binary, 30s intervals, GET/SET tags) | heap_monitor.log, smaps_monitor.log (from orchestrator) |
| C# | `.interval.ndjson` (JSON lines per interval) | Inline `memory` field (gc_heap_bytes, working_set_bytes) + system.ndjson |
| PHP | `.interval.ndjson` (same schema as C#) | Inline `memory` field + system.ndjson |

Java orchestrator additionally produces: mpstat.log, iostat.log, sar_network.log, gc.log, perf_stat.log

## Orchestrator Scripts (differ by branch)
- `java-bench`: `scripts/benchmark_orchestrator.py` — full monitoring, writes to /dev/shm, requires `--skip-infra` if server already running
- `csharp-bench` & `php-bench`: `scripts/run_with_monitor.py` — lighter wrapper, writes system.ndjson alongside metrics

## Plotting

### Unified plot (handles both .hlog and .interval.ndjson):
The script is at `scripts/plot_intervals.py` on csharp-bench/php-bench branches. A unified version that handles .hlog was created during this session (not committed). It requires `hdrhistogram` Python package for .hlog files.

Key design:
- Colors = clients (one color per dataset)
- Line style = commands (solid = GET, dashed = SET, dotted = PING)
- Rolling average smoothing (configurable --window, default 30)
- Y-axis starts from 0
- All throughput in RPS (Java .hlog values divided by interval duration)
- Output: self-contained HTML with Plotly.js (interactive zoom/pan/hover)

### Per-branch plot scripts:
- `java-bench`: `scripts/plot.py` — static PNG via matplotlib, reads .hlog
- `csharp-bench`/`php-bench`: `scripts/plot_intervals.py` — interactive HTML via Plotly.js, reads .interval.ndjson

## Build Commands
```bash
# Java
cd java && mvn -B package -DskipTests
# Version is in java/pom.xml: <valkey-glide.version>X.Y.Z</valkey-glide.version>

# C# (needs cargo in PATH for Glide native lib)
source ~/.cargo/env
dotnet build csharp/src/RespBench/RespBench.csproj -c Release

# PHP (extension must be pre-installed, composer only installs PHP deps)
composer install -d php
```

## C# Driver Config
The csproj uses a NuGet PackageReference:
```xml
<PackageReference Include="Valkey.Glide" Version="1.1.0-rc1" />
```
Previously it used a local ProjectReference to ~/valkey-glide-csharp — this was changed to NuGet.

## PHP Extension Install (from source, for new instances)
Prerequisites: php-dev, rust/cargo, cbindgen, protoc, protobuf-c-compiler, libprotobuf-c-dev
```bash
git clone --recurse-submodules --branch v1.1.0-rc1 https://github.com/valkey-io/valkey-glide-php.git
cd valkey-glide-php
python3 utils/patch_proto_and_rust.py
cd valkey-glide/ffi && cargo build --release && cd ../..
phpize && ./configure --enable-valkey-glide
sudo env PATH=$HOME/.cargo/bin:$PATH CARGO_HOME=$HOME/.cargo RUSTUP_HOME=$HOME/.rustup make build-modules-pre
sudo make install
echo 'extension=valkey_glide.so' | sudo tee /etc/php/8.3/cli/conf.d/20-valkey_glide.ini
```
Note: `pie install valkey-io/valkey-glide-php:1.1.0-rc1` works without sudo (builds fine) but needs sudo for the final .so copy. PECL install requires the .tgz artifact on GitHub releases (not always available for RCs).

## Valkey Server
- Version: 8.1.1 (pre-built at `work/valkey/bin/` on all instances)
- Mode: standalone, port 6379, persistence disabled
- Start: `make server-standalone-start`
- Stop: `make server-standalone-stop`

## Key Observations
- Java ~51K RPS, C# ~44K RPS, PHP ~16K RPS (all 10 connections, same hardware)
- PHP lower latency is misleading — it's due to lower load (single-threaded bottleneck), not better client responsiveness
- C# uses SE.Redis-compatible API layer in Valkey.Glide which adds overhead vs Java's native Glide API
- PHP valkey-glide-php 1.1.0-rc1: logger functions (`valkey_glide_logger_init`) exist but don't produce output (likely not wired in this RC)
- Java Glide debug logs: enabled via `glide.api.logging.Logger.init(Level.DEBUG, "glide-debug.log")` in ValkeyGlideBenchmarkClient.java, writes to `glide-logs/glide-debug.log.<date-hour>` (hourly rotation)

## AMI
- `ami-0b1dde5bcf591e68e` — snapshot of the original instance with all runtimes pre-installed (Java 21, .NET 10, PHP 8.3, Rust, Valkey 8.1.1 built, resp-bench repo cloned)
