<?php

declare(strict_types=1);

namespace RespBench\Metrics;

/**
 * Per-command metrics using reservoir sampling for bounded memory.
 *
 * Instead of storing all latencies (which OOMs on long runs), keeps:
 * - Exact counts, min, max, sum
 * - A fixed-size reservoir sample (10,000 entries) for percentile estimation
 *
 * Reservoir sampling (Algorithm R) gives uniform random samples regardless
 * of stream length, producing accurate percentile estimates.
 */
class CommandMetrics
{
    private const RESERVOIR_SIZE = 10_000;

    public int $requests = 0;
    public int $errors = 0;

    private int $successCount = 0;
    private int $minLatency = PHP_INT_MAX;
    private int $maxLatency = 0;

    /** @var int[] fixed-size reservoir for percentile estimation */
    private array $reservoir = [];
    private bool $sorted = false;

    public function record(int $latencyMicros, bool $success): void
    {
        $this->requests++;
        if (!$success) {
            $this->errors++;
            return;
        }

        $this->successCount++;
        if ($latencyMicros < $this->minLatency) $this->minLatency = $latencyMicros;
        if ($latencyMicros > $this->maxLatency) $this->maxLatency = $latencyMicros;

        // Reservoir sampling (Algorithm R)
        if ($this->successCount <= self::RESERVOIR_SIZE) {
            $this->reservoir[] = $latencyMicros;
        } else {
            $j = mt_rand(0, $this->successCount - 1);
            if ($j < self::RESERVOIR_SIZE) {
                $this->reservoir[$j] = $latencyMicros;
            }
        }
        $this->sorted = false;
    }

    public function count(): int
    {
        return $this->successCount;
    }

    public function min(): int
    {
        return $this->successCount > 0 ? $this->minLatency : 0;
    }

    public function max(): int
    {
        return $this->maxLatency;
    }

    public function percentile(float $p): int
    {
        if (count($this->reservoir) === 0) {
            return 0;
        }
        $this->ensureSorted();
        $n = count($this->reservoir);
        $index = (int) ceil(($p / 100.0) * $n) - 1;
        $index = max(0, min($index, $n - 1));
        return $this->reservoir[$index];
    }

    public function merge(CommandMetrics $other): void
    {
        $this->requests += $other->requests;
        $this->errors += $other->errors;
        if ($other->successCount > 0) {
            if ($other->minLatency < $this->minLatency) $this->minLatency = $other->minLatency;
            if ($other->maxLatency > $this->maxLatency) $this->maxLatency = $other->maxLatency;
        }
        // Merge reservoirs: combine and downsample
        $combined = array_merge($this->reservoir, $other->reservoir);
        if (count($combined) > self::RESERVOIR_SIZE) {
            shuffle($combined);
            $combined = array_slice($combined, 0, self::RESERVOIR_SIZE);
        }
        $this->reservoir = $combined;
        $this->successCount += $other->successCount;
        $this->sorted = false;
    }

    private function ensureSorted(): void
    {
        if (!$this->sorted) {
            sort($this->reservoir);
            $this->sorted = true;
        }
    }
}
