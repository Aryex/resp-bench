<?php

declare(strict_types=1);

namespace RespBench\Engine;

use RespBench\Config\KeyspaceConfig;

/**
 * Key generator for benchmark operations.
 * Produces identical key sequences as the Java reference implementation.
 */
class KeyGenerator
{
    private string $keyPrefix;
    private int $keysCount;
    private int $keySizeBytes;
    private int $counter = 0;
    private JavaRandom $random;

    public function __construct(KeyspaceConfig $config, ?int $seedOverride = null)
    {
        $this->keyPrefix = $config->effectiveKeyPrefix();
        $this->keysCount = $config->keysCount;
        $this->keySizeBytes = $config->keySizeBytes;
        $this->random = new JavaRandom($seedOverride ?? $config->seed ?? 0);
    }

    public function nextKey(): string
    {
        if ($this->keysCount <= 0) {
            return $this->keyPrefix . '0';
        }

        $keyIndex = $this->counter % $this->keysCount;
        $this->counter++;

        return $this->formatKey($keyIndex);
    }

    public function nextRandomKey(): string
    {
        $keyIndex = $this->random->nextInt($this->keysCount);
        return $this->formatKey($keyIndex);
    }

    public function reset(): void
    {
        $this->counter = 0;
    }

    private function formatKey(int $keyIndex): string
    {
        $paddingWidth = max(1, $this->keySizeBytes - strlen($this->keyPrefix));
        return $this->keyPrefix . str_pad((string) $keyIndex, $paddingWidth, '0', STR_PAD_LEFT);
    }
}
