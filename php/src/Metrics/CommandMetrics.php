<?php

declare(strict_types=1);

namespace RespBench\Metrics;

/**
 * Per-command metrics using a simple array-based histogram.
 * PHP doesn't have a native HdrHistogram, so we collect raw latencies
 * and compute percentiles directly.
 */
class CommandMetrics
{
    public int $requests = 0;
    public int $errors = 0;
    /** @var int[] latency values in microseconds */
    private array $latencies = [];
    private bool $sorted = false;

    public function record(int $latencyMicros, bool $success): void
    {
        $this->requests++;
        if ($success) {
            $this->latencies[] = $latencyMicros;
            $this->sorted = false;
        } else {
            $this->errors++;
        }
    }

    public function count(): int
    {
        return count($this->latencies);
    }

    public function min(): int
    {
        return $this->count() > 0 ? min($this->latencies) : 0;
    }

    public function max(): int
    {
        return $this->count() > 0 ? max($this->latencies) : 0;
    }

    public function percentile(float $p): int
    {
        if ($this->count() === 0) {
            return 0;
        }
        $this->ensureSorted();
        $index = (int) ceil(($p / 100.0) * $this->count()) - 1;
        $index = max(0, min($index, $this->count() - 1));
        return $this->latencies[$index];
    }

    /**
     * Merge another CommandMetrics into this one.
     */
    public function merge(CommandMetrics $other): void
    {
        $this->requests += $other->requests;
        $this->errors += $other->errors;
        $this->latencies = array_merge($this->latencies, $other->latencies);
        $this->sorted = false;
    }

    private function ensureSorted(): void
    {
        if (!$this->sorted) {
            sort($this->latencies);
            $this->sorted = true;
        }
    }
}
