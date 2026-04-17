<?php

declare(strict_types=1);

namespace RespBench\Config;

/**
 * Configuration for a benchmark driver (client library).
 */
class DriverConfig
{
    public function __construct(
        public readonly string $schemaVersion = '1.0',
        public readonly ?string $description = null,
        public readonly ?string $driverId = null,
        public readonly string $mode = 'standalone',
        public readonly ?array $tls = null,
        public readonly ?array $auth = null,
        public readonly array $specificDriverConfig = [],
    ) {}

    public function secondaryDriverId(): ?string
    {
        return $this->specificDriverConfig['secondary_driver_id'] ?? null;
    }
}
