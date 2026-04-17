<?php

declare(strict_types=1);

namespace RespBench\Client;

use RespBench\Config\DriverConfig;

/**
 * Abstract interface for benchmark clients.
 * All driver implementations must implement this interface.
 */
abstract class BenchmarkClient
{
    abstract public function connect(string $host, int $port, DriverConfig $config): void;

    abstract public function connected(): bool;

    abstract public function ping(): TimedResult;

    abstract public function get(string $key): TimedResult;

    abstract public function set(string $key, string $value): TimedResult;

    abstract public function del(string $key): TimedResult;

    abstract public function close(): void;

    abstract public function driverVersion(): string;

    /**
     * Measure the execution time of a callable in microseconds.
     */
    protected function measure(callable $fn): TimedResult
    {
        $start = hrtime(true);
        try {
            $result = $fn();
            $latency = (int) ((hrtime(true) - $start) / 1000);
            return new TimedResult($result, $latency);
        } catch (\Throwable $e) {
            $latency = (int) ((hrtime(true) - $start) / 1000);
            return new TimedResult(null, $latency, $e);
        }
    }
}
