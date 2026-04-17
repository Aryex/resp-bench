<?php

declare(strict_types=1);

namespace RespBench\Command;

use RespBench\Client\BenchmarkClient;
use RespBench\Config\CommandConfig;
use RespBench\Engine\KeyGenerator;

/**
 * Factory for creating command executors.
 */
class CommandFactory
{
    private const SUPPORTED = ['ping', 'get', 'set'];

    /**
     * Execute a command and return a result for metrics.
     */
    public static function execute(
        string $command,
        BenchmarkClient $client,
        KeyGenerator $keyGenerator,
        ?int $dataSizeBytes = null,
    ): CommandResult {
        $name = strtoupper($command);

        $result = match ($command) {
            'ping' => $client->ping(),
            'get' => $client->get($keyGenerator->nextKey()),
            'set' => $client->set(
                $keyGenerator->nextKey(),
                str_repeat('x', $dataSizeBytes ?? 64),
            ),
            default => throw new \InvalidArgumentException("Unknown command: {$command}"),
        };

        return new CommandResult(
            commandName: $name,
            latencyMicros: $result->latencyMicros,
            success: $result->isSuccess(),
        );
    }

    /** @return string[] */
    public static function supportedCommands(): array
    {
        return self::SUPPORTED;
    }
}
