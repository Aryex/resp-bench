<?php

declare(strict_types=1);

namespace RespBench\Client;

use RespBench\Client\Impl\ValkeyGlidePhpClient;
use RespBench\Config\DriverConfig;

/**
 * Factory for creating benchmark client instances.
 */
class BenchmarkClientFactory
{
    private const DRIVERS = [
        'valkey-glide-php' => ValkeyGlidePhpClient::class,
    ];

    public static function create(string $driverId): BenchmarkClient
    {
        $class = self::DRIVERS[$driverId] ?? null;
        if (!$class) {
            throw new \InvalidArgumentException(
                "Unknown driver: {$driverId}. Supported: " . implode(', ', array_keys(self::DRIVERS))
            );
        }
        return new $class();
    }

    public static function createAndConnect(string $host, int $port, DriverConfig $config): BenchmarkClient
    {
        $client = self::create($config->driverId);
        $client->connect($host, $port, $config);
        return $client;
    }

    /** @return string[] */
    public static function supportedDrivers(): array
    {
        return array_keys(self::DRIVERS);
    }
}
