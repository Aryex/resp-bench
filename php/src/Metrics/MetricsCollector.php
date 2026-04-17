<?php

declare(strict_types=1);

namespace RespBench\Metrics;

use RespBench\Command\CommandResult;

/**
 * Collects metrics for benchmark operations.
 */
class MetricsCollector
{
    /** @var array<string, CommandMetrics> */
    private array $commandMetrics = [];
    private ?float $startTime = null;
    private ?float $endTime = null;
    private int $totalRequests = 0;
    private int $totalErrors = 0;

    public function start(): void
    {
        $this->startTime = microtime(true);
    }

    public function stop(): void
    {
        $this->endTime = microtime(true);
    }

    public function record(CommandResult $result): void
    {
        $this->totalRequests++;
        if (!$result->success) {
            $this->totalErrors++;
        }

        $name = $result->commandName;
        if (!isset($this->commandMetrics[$name])) {
            $this->commandMetrics[$name] = new CommandMetrics();
        }
        $this->commandMetrics[$name]->record($result->latencyMicros, $result->success);
    }

    public function merge(MetricsCollector $other): void
    {
        $this->totalRequests += $other->totalRequests;
        $this->totalErrors += $other->totalErrors;
        foreach ($other->commandMetrics as $name => $metrics) {
            if (!isset($this->commandMetrics[$name])) {
                $this->commandMetrics[$name] = new CommandMetrics();
            }
            $this->commandMetrics[$name]->merge($metrics);
        }
    }

    public function totalRequests(): int
    {
        return $this->totalRequests;
    }

    public function totalErrors(): int
    {
        return $this->totalErrors;
    }

    public function startTimeIso(): ?string
    {
        return $this->startTime !== null
            ? gmdate('Y-m-d\TH:i:s\Z', (int) $this->startTime)
            : null;
    }

    public function endTimeIso(): ?string
    {
        return $this->endTime !== null
            ? gmdate('Y-m-d\TH:i:s\Z', (int) $this->endTime)
            : null;
    }

    public function durationMillis(): int
    {
        if ($this->startTime === null || $this->endTime === null) {
            return 0;
        }
        return (int) (($this->endTime - $this->startTime) * 1000);
    }

    /** @return array<string, CommandMetrics> */
    public function allMetrics(): array
    {
        return $this->commandMetrics;
    }
}
