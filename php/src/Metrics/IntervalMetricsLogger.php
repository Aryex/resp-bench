<?php

declare(strict_types=1);

namespace RespBench\Metrics;

/**
 * Writes per-interval latency histograms, throughput, and memory to an NDJSON sidecar file.
 *
 * Periodically flushes accumulated metrics and resets counters, producing one NDJSON line
 * per interval. Compatible with scripts/plot_intervals.py for visualization.
 */
class IntervalMetricsLogger
{
    /** @var array<string, IntervalCommandSlot> */
    private array $slots = [];
    private string $outputPath;
    private string $phaseId;
    private float $baseTimeMs;
    private float $lastFlushMs;
    private int $intervalSeconds;

    public function start(string $outputPath, string $phaseId, int $intervalSeconds): void
    {
        $this->outputPath = $outputPath;
        $this->phaseId = $phaseId;
        $this->intervalSeconds = $intervalSeconds;
        $nowMs = microtime(true) * 1000;
        $this->baseTimeMs = $nowMs;
        $this->lastFlushMs = $nowMs;

        $dir = dirname($outputPath);
        if (!is_dir($dir)) {
            mkdir($dir, 0755, true);
        }
    }

    /**
     * Record a latency value for a command.
     */
    public function recordValue(string $commandName, int $latencyMicros, bool $success): void
    {
        if (!isset($this->slots[$commandName])) {
            $this->slots[$commandName] = new IntervalCommandSlot();
        }
        $slot = $this->slots[$commandName];
        $slot->requests++;
        if ($success) {
            $slot->latencies[] = $latencyMicros;
        } else {
            $slot->errors++;
        }
    }

    /**
     * Check if it's time to flush and do so if needed.
     * Call this periodically from the benchmark loop.
     */
    public function maybeFlush(): void
    {
        $nowMs = microtime(true) * 1000;
        if (($nowMs - $this->lastFlushMs) >= ($this->intervalSeconds * 1000)) {
            $this->flush();
        }
    }

    public function stop(): void
    {
        $this->flush();
    }

    private function flush(): void
    {
        $nowMs = microtime(true) * 1000;
        $intervalStartMs = $this->lastFlushMs;
        $this->lastFlushMs = $nowMs;

        $durationS = ($nowMs - $intervalStartMs) / 1000.0;
        $elapsedS = ($nowMs - $this->baseTimeMs) / 1000.0;

        $root = [
            'phase_id' => $this->phaseId,
            'interval' => [
                'start_timestamp' => gmdate('Y-m-d\TH:i:s\Z', (int) ($intervalStartMs / 1000)),
                'end_timestamp' => gmdate('Y-m-d\TH:i:s\Z', (int) ($nowMs / 1000)),
                'elapsed_s' => round($elapsedS, 1),
                'duration_s' => round($durationS, 1),
            ],
        ];

        $metrics = [];
        $hasData = false;

        foreach ($this->slots as $cmdName => $slot) {
            if ($slot->requests === 0) {
                continue;
            }
            $hasData = true;

            $cmdNode = [
                'requests' => $slot->requests,
                'errors' => $slot->errors,
            ];

            $latency = [
                'unit' => 'us',
                'count' => count($slot->latencies),
            ];

            if (count($slot->latencies) > 0) {
                sort($slot->latencies);
                $count = count($slot->latencies);
                $latency['summary'] = [
                    'min' => $slot->latencies[0],
                    'p50' => $slot->latencies[(int) ($count * 0.50) - 1] ?? 0,
                    'p95' => $slot->latencies[(int) ceil($count * 0.95) - 1] ?? 0,
                    'p99' => $slot->latencies[(int) ceil($count * 0.99) - 1] ?? 0,
                    'p999' => $slot->latencies[(int) ceil($count * 0.999) - 1] ?? 0,
                    'max' => $slot->latencies[$count - 1],
                ];
            }

            $cmdNode['latency'] = $latency;
            $metrics[$cmdName] = $cmdNode;

            // Reset slot
            $slot->requests = 0;
            $slot->errors = 0;
            $slot->latencies = [];
        }

        if (!$hasData) {
            return;
        }

        $root['metrics'] = $metrics;

        // Memory snapshot
        $root['memory'] = [
            'gc_heap_bytes' => memory_get_usage(false),      // PHP heap (emalloc)
            'working_set_bytes' => memory_get_usage(true),   // PHP allocated from OS
            'peak_heap_bytes' => memory_get_peak_usage(false),
            'peak_working_set_bytes' => memory_get_peak_usage(true),
        ];

        $json = json_encode($root, JSON_THROW_ON_ERROR);
        file_put_contents($this->outputPath, $json . "\n", FILE_APPEND);
    }
}

class IntervalCommandSlot
{
    public int $requests = 0;
    public int $errors = 0;
    /** @var int[] */
    public array $latencies = [];
}
