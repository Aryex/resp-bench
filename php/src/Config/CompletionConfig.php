<?php

declare(strict_types=1);

namespace RespBench\Config;

class CompletionConfig
{
    public function __construct(
        public readonly string $type,
        public readonly ?int $seconds = null,
        public readonly ?int $requests = null,
    ) {}

    public function isRequestBased(): bool
    {
        return $this->type === 'requests';
    }

    public function isDurationBased(): bool
    {
        return $this->type === 'duration';
    }
}
