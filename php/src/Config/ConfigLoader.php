<?php

declare(strict_types=1);

namespace RespBench\Config;

/**
 * Loads configuration from JSON files.
 */
class ConfigLoader
{
    public static function loadDriverConfig(string $path): DriverConfig
    {
        $json = self::parseJsonFile($path);
        return self::parseDriverConfig($json);
    }

    public static function loadWorkloadConfig(string $path): WorkloadConfig
    {
        $json = self::parseJsonFile($path);
        return self::parseWorkloadConfig($json);
    }

    public static function parseDriverConfig(array $json): DriverConfig
    {
        return new DriverConfig(
            schemaVersion: $json['schema_version'] ?? '1.0',
            description: $json['description'] ?? null,
            driverId: $json['driver_id'] ?? null,
            mode: $json['mode'] ?? 'standalone',
            tls: $json['tls'] ?? null,
            auth: $json['auth'] ?? null,
            specificDriverConfig: $json['specific_driver_config'] ?? [],
        );
    }

    public static function parseWorkloadConfig(array $json): WorkloadConfig
    {
        $phases = array_map(
            fn(array $p) => self::parsePhaseConfig($p),
            $json['phases'] ?? []
        );

        return new WorkloadConfig(
            schemaVersion: $json['schema_version'] ?? '1.0',
            benchmarkProfile: $json['benchmark_profile'] ?? [],
            phases: $phases,
        );
    }

    private static function parsePhaseConfig(array $json): PhaseConfig
    {
        return new PhaseConfig(
            id: $json['id'],
            description: $json['description'] ?? null,
            connections: $json['connections'] ?? 1,
            cpsLimit: $json['cps_limit'] ?? -1,
            rpsLimit: $json['rps_limit'] ?? -1,
            pipelineDepth: $json['pipeline_depth'] ?? 1,
            warmupRequests: $json['warmup_requests'] ?? 1,
            completion: isset($json['completion']) ? self::parseCompletionConfig($json['completion']) : null,
            keyspace: isset($json['keyspace']) ? self::parseKeyspaceConfig($json['keyspace']) : null,
            commands: array_map(fn(array $c) => self::parseCommandConfig($c), $json['commands'] ?? []),
        );
    }

    private static function parseCompletionConfig(array $json): CompletionConfig
    {
        return new CompletionConfig(
            type: $json['type'],
            seconds: $json['seconds'] ?? null,
            requests: $json['requests'] ?? null,
        );
    }

    private static function parseKeyspaceConfig(array $json): KeyspaceConfig
    {
        return new KeyspaceConfig(
            keysCount: $json['keys_count'],
            keySizeBytes: $json['key_size_bytes'],
            keyPrefix: $json['key_prefix'] ?? null,
            generationAlg: $json['generation_alg'] ?? 'sequential_int',
            seed: $json['seed'] ?? null,
        );
    }

    private static function parseCommandConfig(array $json): CommandConfig
    {
        return new CommandConfig(
            command: $json['command'],
            weight: (float) $json['weight'],
            dataSizeBytes: $json['data_size_bytes'] ?? null,
        );
    }

    private static function parseJsonFile(string $path): array
    {
        $content = file_get_contents($path);
        if ($content === false) {
            throw new \RuntimeException("Cannot read file: {$path}");
        }
        $json = json_decode($content, true, 512, JSON_THROW_ON_ERROR);
        return $json;
    }
}
