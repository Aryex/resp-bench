# Spec: Fix C# IntervalMetricsLogger race condition using HdrHistogram Recorder

## Context

The C# engine's `IntervalMetricsLogger` crashed after ~8 hours into a 1-week benchmark with:
```
System.InvalidOperationException: Source has been modified during enumeration.
   at HdrHistogram.Iteration.AbstractHistogramEnumerator.Next()
   at HdrHistogram.HistogramExtensions.GetMaxValue(HistogramBase histogram)
   at RespBench.Metrics.IntervalMetricsLogger.Flush() line 111
```

### Root Cause

The current code uses `Interlocked.Exchange` to atomically swap a `LongConcurrentHistogram` with a fresh one, then reads from the returned snapshot:

```csharp
// RecordValue (worker threads):
slot.Histogram.RecordValue(...);
//    ^^^^^^^^^ reads field, then calls RecordValue on the captured reference

// Flush (timer thread):
var snapshot = Interlocked.Exchange(ref slot.Histogram, fresh);
snapshot.GetMaxValue();  // enumerates → throws if concurrent write
```

The race: a worker thread reads `slot.Histogram` (capturing reference X), the timer thread swaps `slot.Histogram` to Y and starts enumerating X, then the worker calls `X.RecordValue(...)` using its captured reference. The enumerator detects the modification and throws.

`LongConcurrentHistogram` supports concurrent writes but its iterator-based reads (`GetMaxValue`, `GetValueAtPercentile`) are not safe while writes are in flight on the same instance.

## Goal

Replace the manual swap-and-read pattern with HdrHistogram.NET's `Recorder` class, which is designed exactly for this writer/reader separation via internal double-buffering.

## Files to Modify

- `csharp/src/RespBench/Metrics/IntervalMetricsLogger.cs`

## Branch

Work on `csharp-bench`. Create a new branch like `csharp-bench/fix-interval-logger-race` off of `csharp-bench`.

## Implementation

### 1. Verify HdrHistogram.NET Recorder API

The spec assumes HdrHistogram.NET 1.x has a `Recorder` class accessible via `HistogramFactory`. Before coding, verify the exact API:

```bash
# On a dev machine with the repo checked out
cd csharp
dotnet add src/RespBench/RespBench.csproj package HdrHistogram  # already a dep
# Check available types
grep -r "Recorder\|HistogramFactory\|WithThreadSafeWrites" ~/.nuget/packages/hdrhistogram/
```

Expected API (based on HdrHistogram.NET convention):
```csharp
var recorder = HistogramFactory
    .With64BitBucketSize()
    .WithValuesFrom(1)
    .WithValuesUpTo(MaxLatencyMicros)
    .WithPrecisionOf(3)
    .WithThreadSafeWrites()
    .WithThreadSafeReads()
    .Create();

recorder.RecordValue(latencyMicros);           // from workers
HistogramBase snapshot = recorder.GetIntervalHistogram();  // from flush timer
```

If the API differs, adapt accordingly. The key requirement is a type that:
- Accepts concurrent `RecordValue(long)` calls from worker threads
- Provides a `GetIntervalHistogram()` (or similar) that returns a safe-to-read snapshot representing all records since the last call, without racing with concurrent writers

### 2. Replace HistogramSlot

Current:
```csharp
private class HistogramSlot
{
    public LongConcurrentHistogram Histogram = new(1, MaxLatencyMicros, 3);
    public long Requests;
    public long Errors;
}
```

New:
```csharp
private class HistogramSlot
{
    public Recorder Recorder = HistogramFactory
        .With64BitBucketSize()
        .WithValuesFrom(1)
        .WithValuesUpTo(MaxLatencyMicros)
        .WithPrecisionOf(3)
        .WithThreadSafeWrites()
        .WithThreadSafeReads()
        .Create();
    public long Requests;
    public long Errors;
}
```

### 3. Update RecordValue

Current:
```csharp
public void RecordValue(string commandName, long latencyMicros, bool success)
{
    var slot = _slots.GetOrAdd(commandName, _ => new HistogramSlot());
    if (success)
        slot.Histogram.RecordValue(Math.Max(1, Math.Min(latencyMicros, MaxLatencyMicros)));
    else
        Interlocked.Increment(ref slot.Errors);
    Interlocked.Increment(ref slot.Requests);
}
```

New:
```csharp
public void RecordValue(string commandName, long latencyMicros, bool success)
{
    var slot = _slots.GetOrAdd(commandName, _ => new HistogramSlot());
    if (success)
        slot.Recorder.RecordValue(Math.Max(1, Math.Min(latencyMicros, MaxLatencyMicros)));
    else
        Interlocked.Increment(ref slot.Errors);
    Interlocked.Increment(ref slot.Requests);
}
```

### 4. Update Flush

Current (the buggy code):
```csharp
foreach (var (cmdName, slot) in _slots)
{
    var fresh = new LongConcurrentHistogram(1, MaxLatencyMicros, 3);
    var snapshot = Interlocked.Exchange(ref slot.Histogram, fresh);
    long requests = Interlocked.Exchange(ref slot.Requests, 0);
    long errors = Interlocked.Exchange(ref slot.Errors, 0);

    if (requests == 0) continue;
    hasData = true;

    // ... build cmdNode ...
    if (snapshot.TotalCount > 0)
    {
        latency["summary"] = new JsonObject
        {
            ["min"] = snapshot.GetValueAtPercentile(0),
            ["p50"] = snapshot.GetValueAtPercentile(50),
            // ...
            ["max"] = snapshot.GetMaxValue()  // ← throws here under contention
        };
        // ...
    }
}
```

New:
```csharp
foreach (var (cmdName, slot) in _slots)
{
    HistogramBase snapshot = slot.Recorder.GetIntervalHistogram();
    long requests = Interlocked.Exchange(ref slot.Requests, 0);
    long errors = Interlocked.Exchange(ref slot.Errors, 0);

    if (requests == 0) continue;
    hasData = true;

    // ... same as before, but operating on `snapshot` which is safe to read ...
}
```

All the `snapshot.GetValueAtPercentile(...)`, `snapshot.GetMaxValue()`, `snapshot.TotalCount`, and `EncodeHistogram(snapshot)` calls should work unchanged because `GetIntervalHistogram()` returns a `HistogramBase` that's a stable snapshot.

### 5. Remove unused imports if any

The `LongConcurrentHistogram` import may no longer be needed if nothing else in the file uses it. Clean up.

## Testing

### Unit test
Add a test that exercises the race condition:
- `csharp/test/RespBench.Tests/Metrics/IntervalMetricsLoggerConcurrencyTest.cs`
- Spawn N=8 worker tasks recording values continuously for 5 seconds
- Timer flushes every 100ms in the background
- Assert: no exceptions thrown, output file has expected number of interval lines

```csharp
[Fact]
public async Task Flush_UnderConcurrentWrites_DoesNotThrow()
{
    var logger = new IntervalMetricsLogger();
    var tmpFile = Path.GetTempFileName();
    logger.Start(tmpFile, "TEST", intervalSeconds: 1);

    var cts = new CancellationTokenSource(TimeSpan.FromSeconds(5));
    var workers = Enumerable.Range(0, 8).Select(_ => Task.Run(() =>
    {
        var rng = new Random();
        while (!cts.IsCancellationRequested)
        {
            logger.RecordValue("GET", rng.Next(1, 10000), true);
        }
    })).ToArray();

    await Task.WhenAll(workers);
    logger.Stop();

    // Verify no data corruption: file has valid NDJSON lines
    var lines = File.ReadAllLines(tmpFile).Where(l => !string.IsNullOrEmpty(l));
    Assert.NotEmpty(lines);
    foreach (var line in lines)
    {
        var doc = JsonDocument.Parse(line); // throws if invalid
    }
    File.Delete(tmpFile);
}
```

### Integration test
Run a short benchmark end-to-end:
```bash
cd resp-bench
make server-standalone-start
dotnet run --project csharp/src/RespBench/RespBench.csproj -c Release -- \
  --server localhost:6379 \
  --driver configs/drivers/default/stackexchange-redis.json \
  --workload configs/workloads/test-30s.json \
  --metrics /tmp/test.ndjson
```
Verify no exceptions, and `/tmp/test.ndjson.STEADY.interval.ndjson` contains ~30 well-formed lines.

### Long-running validation
The original crash happened after ~8 hours. After the fix, run a 24-hour test to validate stability:
```bash
# On the C# EC2 instance (3.235.62.223)
ssh -i ~/.ssh/lehminh.pem ubuntu@3.235.62.223
cd ~/resp-bench
git fetch && git checkout csharp-bench/fix-interval-logger-race
source ~/.cargo/env
tmux new-session -d -s bench-24h 'python3 scripts/run_with_monitor.py \
  --server localhost:6379 \
  --driver configs/drivers/default/valkey-glide-csharp.json \
  --workload configs/workloads/glide-stability-24h.json \
  --output-dir output/csharp-24h-fix 2>&1 | tee output/csharp-24h-fix-stdout.log'
```

## Edge Cases to Handle

1. **Recorder with zero records**: `GetIntervalHistogram()` on a recorder with no records should return an empty histogram. The existing `if (snapshot.TotalCount > 0)` check handles this.

2. **Memory allocation**: Each `GetIntervalHistogram()` may allocate a new histogram internally. Over a 1-week run (2M+ intervals across all commands), this could add GC pressure. If it becomes a concern, check if HdrHistogram.NET supports a `GetIntervalHistogram(HistogramBase)` overload that reuses a caller-provided buffer.

3. **Stop() ordering**: `Stop()` disposes the timer then calls `Flush()` one last time. Ensure the final `GetIntervalHistogram()` captures any records that happened during the last interval before shutdown. The Recorder pattern handles this correctly.

## Verification Checklist

Before submitting:
- [ ] `dotnet build csharp -c Release` succeeds with no warnings
- [ ] `dotnet test csharp` passes including the new concurrency test
- [ ] Integration test (30s run) produces valid NDJSON output with ~30 intervals
- [ ] No `InvalidOperationException` in logs during a 1-hour soak test
- [ ] Throughput is within ±5% of pre-fix baseline (~44K RPS at 10 connections)

## Rollback

If the Recorder API differs or introduces unexpected issues, fallback to Option 2 from the analysis (brief drain after swap): add `Thread.Sleep(10)` between the `Interlocked.Exchange` and the first read. Pragmatic, not architecturally clean, but eliminates the race in practice.

## References

- HdrHistogram Java Recorder pattern (conceptually identical): https://github.com/HdrHistogram/HdrHistogram/blob/master/src/main/java/org/HdrHistogram/Recorder.java
- HdrHistogram.NET repo: https://github.com/HdrHistogram/HdrHistogram.NET
- The buggy file in our repo: `csharp/src/RespBench/Metrics/IntervalMetricsLogger.cs` (commit at time of crash: see `csharp-bench` HEAD)
- Original crash log: available at `~/resp-bench/output/csharp-1w-rc1-monitored/console.log` on instance `3.235.62.223`
