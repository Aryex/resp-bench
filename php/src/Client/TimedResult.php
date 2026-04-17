<?php

declare(strict_types=1);

namespace RespBench\Client;

/**
 * Result of a timed operation, including latency and optional error.
 */
class TimedResult
{
    public function __construct(
        public readonly mixed $value,
        public readonly int $latencyMicros,
        public readonly ?\Throwable $error = null,
    ) {}

    public function isSuccess(): bool
    {
        return $this->error === null;
    }
}
