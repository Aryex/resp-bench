# resp-bench PHP Engine

PHP implementation of the resp-bench benchmark suite using the [valkey-glide PHP extension](https://github.com/valkey-io/valkey-glide-php).

## Prerequisites

- PHP 8.1+
- Composer
- `valkey_glide` PHP extension installed and enabled

### Installing the valkey_glide extension

The extension must be built from source. See the [valkey-glide-php DEVELOPER.md](https://github.com/valkey-io/valkey-glide-php/blob/main/DEVELOPER.md) for build instructions.

## Supported Drivers

| Driver | Extension | Description |
|--------|-----------|-------------|
| valkey-glide-php | ext-valkey_glide | Valkey GLIDE PHP client |

## Supported Commands

- `ping` — PING
- `get` — GET
- `set` — SET (with configurable data_size_bytes)

## Installation

```bash
make php-build
# or
cd php && composer install
```

## Usage

```bash
# Run a benchmark
make php-run \
  DRIVER=configs/drivers/default/valkey-glide-php.json \
  WORKLOAD=configs/workloads/example-workload.json \
  SERVER=localhost:6379

# Show supported drivers and commands
make php-info

# Run unit tests
make php-test
```

## Architecture

```
php/
├── bin/
│   └── resp-bench              # CLI entry point
├── src/
│   ├── Client/
│   │   ├── BenchmarkClient.php         # Abstract client interface
│   │   ├── BenchmarkClientFactory.php  # Client factory
│   │   ├── TimedResult.php             # Timed operation result
│   │   └── Impl/
│   │       └── ValkeyGlidePhpClient.php  # valkey-glide implementation
│   ├── Command/
│   │   ├── CommandFactory.php          # Command executor
│   │   └── CommandResult.php           # Command result
│   ├── Config/
│   │   ├── ConfigLoader.php            # JSON config parser
│   │   ├── DriverConfig.php            # Driver config model
│   │   ├── WorkloadConfig.php          # Workload config model
│   │   ├── PhaseConfig.php             # Phase config model
│   │   ├── KeyspaceConfig.php          # Keyspace config model
│   │   ├── CommandConfig.php           # Command config model
│   │   └── CompletionConfig.php        # Completion criteria model
│   ├── Engine/
│   │   ├── BenchmarkEngine.php         # Main orchestrator
│   │   ├── KeyGenerator.php            # Key generation
│   │   ├── JavaRandom.php              # Java-compatible LCG PRNG
│   │   ├── RateLimiter.php             # Token bucket rate limiter
│   │   └── CommandSelector.php         # Weighted random command selection
│   └── Metrics/
│       ├── MetricsCollector.php        # Latency collection
│       ├── CommandMetrics.php          # Per-command metrics with percentiles
│       └── NdjsonWriter.php            # NDJSON output writer
├── test/
│   └── unit/
│       ├── KeyGeneratorTest.php
│       ├── ConfigLoaderTest.php
│       └── RateLimiterTest.php
├── composer.json
└── phpunit.xml
```

## Concurrency Model

PHP is single-threaded, so each benchmark process runs one client per connection sequentially. For multi-connection benchmarks, the matrix orchestrator spawns separate PHP processes per connection count. This is similar to how the Ruby engine works in process mode.

## Adding a New PHP Driver

1. Create a new class in `src/Client/Impl/` extending `BenchmarkClient`
2. Implement `connect()`, `ping()`, `get()`, `set()`, `del()`, `close()`, `driverVersion()`
3. Register it in `BenchmarkClientFactory::DRIVERS`
4. Create a driver config JSON in `configs/drivers/default/`
