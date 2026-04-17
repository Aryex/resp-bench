<?php

declare(strict_types=1);

namespace RespBench\Config;

class WorkloadConfig
{
    /**
     * @param PhaseConfig[] $phases
     */
    public function __construct(
        public readonly string $schemaVersion = '1.0',
        public readonly array $benchmarkProfile = [],
        public readonly array $phases = [],
    ) {}

    public function name(): string
    {
        return $this->benchmarkProfile['name'] ?? 'unnamed';
    }
}
