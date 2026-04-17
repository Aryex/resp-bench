<?php

declare(strict_types=1);

namespace RespBench\Config;

class CommandConfig
{
    public function __construct(
        public readonly string $command,
        public readonly float $weight,
        public readonly ?int $dataSizeBytes = null,
    ) {}
}
