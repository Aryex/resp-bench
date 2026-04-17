<?php

declare(strict_types=1);

namespace RespBench\Tests\Unit;

use PHPUnit\Framework\TestCase;
use RespBench\Config\ConfigLoader;

class ConfigLoaderTest extends TestCase
{
    public function testParseDriverConfig(): void
    {
        $json = [
            'schema_version' => '1.0',
            'description' => 'test driver',
            'driver_id' => 'valkey-glide-php',
            'mode' => 'standalone',
            'specific_driver_config' => [],
        ];

        $config = ConfigLoader::parseDriverConfig($json);

        $this->assertSame('valkey-glide-php', $config->driverId);
        $this->assertSame('standalone', $config->mode);
    }

    public function testParseWorkloadConfig(): void
    {
        $json = [
            'schema_version' => '1.0',
            'benchmark_profile' => ['name' => 'test'],
            'phases' => [
                [
                    'id' => 'STEADY',
                    'connections' => 4,
                    'completion' => ['type' => 'requests', 'requests' => 1000],
                    'keyspace' => [
                        'keys_count' => 100,
                        'key_size_bytes' => 16,
                        'generation_alg' => 'sequential_int',
                    ],
                    'commands' => [
                        ['command' => 'set', 'weight' => 0.5, 'data_size_bytes' => 64],
                        ['command' => 'get', 'weight' => 0.5],
                    ],
                ],
            ],
        ];

        $config = ConfigLoader::parseWorkloadConfig($json);

        $this->assertSame('test', $config->name());
        $this->assertCount(1, $config->phases);
        $this->assertSame('STEADY', $config->phases[0]->id);
        $this->assertSame(4, $config->phases[0]->connections);
        $this->assertCount(2, $config->phases[0]->commands);
    }
}
