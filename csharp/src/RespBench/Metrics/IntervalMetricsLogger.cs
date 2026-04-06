/*
 * Copyright 2025 the original author or authors.
 */
using System.Collections.Concurrent;
using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Nodes;
using HdrHistogram;
using HdrHistogram.Encoding;
using HdrHistogram.Utilities;

namespace RespBench.Metrics;

/// <summary>
/// Writes per-interval latency histograms to an NDJSON sidecar file.
///
/// Each command gets its own LongConcurrentHistogram for lock-free concurrent recording.
/// A background timer periodically swaps the active histogram with a fresh one and writes
/// the interval snapshot as a single NDJSON line.
/// </summary>
public class IntervalMetricsLogger
{
    private const long MaxLatencyMicros = 600_000_000L;

    private readonly ConcurrentDictionary<string, HistogramSlot> _slots = new();
    private Timer? _timer;
    private string _outputPath = "";
    private string _phaseId = "";
    private long _baseTimeMs;
    private long _lastFlushMs;

    public void Start(string outputPath, string phaseId, int intervalSeconds)
    {
        _outputPath = outputPath;
        _phaseId = phaseId;
        _baseTimeMs = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
        _lastFlushMs = _baseTimeMs;

        // Ensure parent directory exists
        var dir = Path.GetDirectoryName(outputPath);
        if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);

        _timer = new Timer(_ => Flush(), null,
            TimeSpan.FromSeconds(intervalSeconds),
            TimeSpan.FromSeconds(intervalSeconds));
    }

    /// <summary>Record a latency value for a command. Thread-safe.</summary>
    public void RecordValue(string commandName, long latencyMicros, bool success)
    {
        var slot = _slots.GetOrAdd(commandName, _ => new HistogramSlot());
        if (success)
            slot.Histogram.RecordValue(Math.Max(1, Math.Min(latencyMicros, MaxLatencyMicros)));
        else
            Interlocked.Increment(ref slot.Errors);
        Interlocked.Increment(ref slot.Requests);
    }

    public void Stop()
    {
        _timer?.Dispose();
        _timer = null;
        Flush();
    }

    private void Flush()
    {
        long now = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
        long intervalStartMs = _lastFlushMs;
        _lastFlushMs = now;

        var root = new JsonObject
        {
            ["phase_id"] = _phaseId,
            ["interval"] = new JsonObject
            {
                ["start_timestamp"] = DateTimeOffset.FromUnixTimeMilliseconds(intervalStartMs).ToString("o"),
                ["end_timestamp"] = DateTimeOffset.FromUnixTimeMilliseconds(now).ToString("o"),
                ["elapsed_s"] = Math.Round((now - _baseTimeMs) / 1000.0, 1),
                ["duration_s"] = Math.Round((now - intervalStartMs) / 1000.0, 1)
            }
        };

        var metrics = new JsonObject();
        bool hasData = false;

        foreach (var (cmdName, slot) in _slots)
        {
            var fresh = new LongConcurrentHistogram(1, MaxLatencyMicros, 3);
            var snapshot = Interlocked.Exchange(ref slot.Histogram, fresh);
            long requests = Interlocked.Exchange(ref slot.Requests, 0);
            long errors = Interlocked.Exchange(ref slot.Errors, 0);

            if (requests == 0) continue;
            hasData = true;

            var cmdNode = new JsonObject
            {
                ["requests"] = requests,
                ["errors"] = errors
            };

            var latency = new JsonObject
            {
                ["unit"] = "us",
                ["count"] = snapshot.TotalCount
            };

            if (snapshot.TotalCount > 0)
            {
                latency["summary"] = new JsonObject
                {
                    ["min"] = snapshot.GetValueAtPercentile(0),
                    ["p50"] = snapshot.GetValueAtPercentile(50),
                    ["p95"] = snapshot.GetValueAtPercentile(95),
                    ["p99"] = snapshot.GetValueAtPercentile(99),
                    ["p999"] = snapshot.GetValueAtPercentile(99.9),
                    ["max"] = snapshot.GetMaxValue()
                };
                latency["hdr"] = new JsonObject
                {
                    ["format"] = "hdr",
                    ["sigfig"] = 3,
                    ["payload_b64"] = EncodeHistogram(snapshot)
                };
            }

            cmdNode["latency"] = latency;
            metrics[cmdName] = cmdNode;
        }

        if (!hasData) return;

        root["metrics"] = metrics;

        // Memory snapshot
        var proc = Process.GetCurrentProcess();
        var gcInfo = GC.GetGCMemoryInfo();
        root["memory"] = new JsonObject
        {
            ["gc_heap_bytes"] = GC.GetTotalMemory(false),
            ["working_set_bytes"] = proc.WorkingSet64,
            ["private_bytes"] = proc.PrivateMemorySize64,
            ["gc_heap_size_bytes"] = gcInfo.HeapSizeBytes,
            ["gc_committed_bytes"] = gcInfo.TotalCommittedBytes
        };
        string json = root.ToJsonString(new JsonSerializerOptions { WriteIndented = false });
        try { File.AppendAllText(_outputPath, json + Environment.NewLine); }
        catch { /* best-effort */ }
    }

    private static string EncodeHistogram(HistogramBase histogram)
    {
        try
        {
            int neededCapacity = histogram.GetNeededByteBufferCapacity();
            var buffer = ByteBuffer.Allocate(neededCapacity);
            int bytesWritten = histogram.Encode(buffer, HistogramEncoderV2.Instance);
            buffer.Position = 0;
            byte[] bytes = new byte[bytesWritten];
            for (int i = 0; i < bytesWritten; i++)
                bytes[i] = buffer.Get();
            return Convert.ToBase64String(bytes);
        }
        catch { return ""; }
    }

    private class HistogramSlot
    {
        public LongConcurrentHistogram Histogram = new(1, MaxLatencyMicros, 3);
        public long Requests;
        public long Errors;
    }
}
