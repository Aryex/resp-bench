<?php

declare(strict_types=1);

namespace RespBench\Config;

class KeyspaceConfig
{
    public function __construct(
        public readonly int $keysCount,
        public readonly int $keySizeBytes,
        public readonly ?string $keyPrefix = null,
        public readonly string $generationAlg = 'sequential_int',
        public readonly ?int $seed = null,
    ) {}

    public function effectiveKeyPrefix(): string
    {
        return $this->keyPrefix ?? 'key:';
    }

    public function isSequential(): bool
    {
        return $this->generationAlg === 'sequential_int';
    }
}
