<?php

declare(strict_types=1);

namespace RespBench\Config;

class PhaseConfig
{
    /**
     * @param CommandConfig[] $commands
     */
    public function __construct(
        public readonly string $id,
        public readonly ?string $description = null,
        public readonly int $connections = 1,
        public readonly int $cpsLimit = -1,
        public readonly int $rpsLimit = -1,
        public readonly int $pipelineDepth = 1,
        public readonly int $warmupRequests = 1,
        public readonly ?CompletionConfig $completion = null,
        public readonly ?KeyspaceConfig $keyspace = null,
        public readonly array $commands = [],
    ) {}
}
