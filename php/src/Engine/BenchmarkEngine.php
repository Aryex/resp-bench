<?php

declare(strict_types=1);

namespace RespBench\Engine;

use RespBench\Client\BenchmarkClient;
use RespBench\Client\BenchmarkClientFactory;
use RespBench\Command\CommandFactory;
use RespBench\Config\DriverConfig;
use RespBench\Config\PhaseConfig;
use RespBench\Config\WorkloadConfig;
use RespBench\Metrics\MetricsCollector;
use RespBench\Metrics\NdjsonWriter;

/**
 * Main benchmark engine that orchestrates the benchmark execution.
 *
 * PHP is single-threaded, so each "connection" is a separate client instance
 * executing commands sequentially. For multi-connection benchmarks, the matrix
 * orchestrator spawns separate PHP processes.
 */
class BenchmarkEngine
{
    private NdjsonWriter $metricsWriter;

    public function __construct(
        private readonly string $host,
        private readonly int $port,
        private readonly DriverConfig $driverConfig,
        private readonly WorkloadConfig $workloadConfig,
        private readonly string $metricsPath,
        private readonly ?string $commitId = null,
    ) {
        $this->metricsWriter = new NdjsonWriter($metricsPath);
    }

    public function run(): void
    {
        $this->log("Starting benchmark: {$this->workloadConfig->name()}");
        $this->log("Driver: {$this->driverConfig->driverId}, Mode: {$this->driverConfig->mode}");
        $this->log("Server: {$this->host}:{$this->port}");

        $this->setupMetadata();

        foreach ($this->workloadConfig->phases as $phase) {
            $this->executePhase($phase);
        }

        $this->log("Benchmark completed");
    }

    private function setupMetadata(): void
    {
        $sampleClient = BenchmarkClientFactory::createAndConnect(
            $this->host, $this->port, $this->driverConfig
        );

        $this->metricsWriter->setMetadata(
            commitId: $this->commitId,
            driverId: $this->driverConfig->driverId,
            primaryDriverVersion: $sampleClient->driverVersion(),
        );

        $this->log("Driver version: {$sampleClient->driverVersion()}");
        $sampleClient->close();
    }

    private function executePhase(PhaseConfig $phase): void
    {
        $this->log("Phase [{$phase->id}]: connections={$phase->connections}");

        // Create client connections
        $clients = [];
        for ($i = 0; $i < $phase->connections; $i++) {
            $clients[] = BenchmarkClientFactory::createAndConnect(
                $this->host, $this->port, $this->driverConfig
            );
        }

        // Warmup
        $this->warmup($clients, $phase->warmupRequests);

        // Setup
        $keyGenerator = new KeyGenerator($phase->keyspace);
        $commandSelector = new CommandSelector($phase->commands);
        $rateLimiter = RateLimiter::create($phase->rpsLimit);
        $collector = new MetricsCollector();

        // Run workload
        $collector->start();
        $status = 'COMPLETED';

        try {
            if ($phase->completion->isRequestBased()) {
                $this->runRequestBased($clients, $phase, $keyGenerator, $commandSelector, $rateLimiter, $collector);
            } else {
                $this->runDurationBased($clients, $phase, $keyGenerator, $commandSelector, $rateLimiter, $collector);
            }
        } catch (\Throwable $e) {
            $status = 'ERROR';
            $this->log("Phase [{$phase->id}] error: {$e->getMessage()}");
        }

        $collector->stop();

        // Write results
        $this->metricsWriter->writePhaseResults(
            $phase->id, $status, $phase->connections, $collector
        );

        $rps = $collector->durationMillis() > 0
            ? (int) ($collector->totalRequests() / ($collector->durationMillis() / 1000.0))
            : 0;
        $this->log("Phase [{$phase->id}]: {$collector->totalRequests()} requests, {$rps} RPS, {$collector->totalErrors()} errors");

        // Cleanup
        foreach ($clients as $client) {
            $client->close();
        }
    }

    /**
     * @param BenchmarkClient[] $clients
     */
    private function warmup(array $clients, int $warmupRequests): void
    {
        $perClient = max(1, (int) ($warmupRequests / count($clients)));
        foreach ($clients as $client) {
            for ($i = 0; $i < $perClient; $i++) {
                $client->ping();
            }
        }
    }

    /**
     * @param BenchmarkClient[] $clients
     */
    private function runRequestBased(
        array $clients,
        PhaseConfig $phase,
        KeyGenerator $keyGenerator,
        CommandSelector $commandSelector,
        ?RateLimiter $rateLimiter,
        MetricsCollector $collector,
    ): void {
        $totalRequests = $phase->completion->requests;
        $clientCount = count($clients);
        $completed = 0;

        while ($completed < $totalRequests) {
            $client = $clients[$completed % $clientCount];
            $rateLimiter?->acquire();

            $cmd = $commandSelector->select();
            $result = CommandFactory::execute(
                $cmd->command, $client, $keyGenerator, $cmd->dataSizeBytes
            );
            $collector->record($result);
            $completed++;
        }
    }

    /**
     * @param BenchmarkClient[] $clients
     */
    private function runDurationBased(
        array $clients,
        PhaseConfig $phase,
        KeyGenerator $keyGenerator,
        CommandSelector $commandSelector,
        ?RateLimiter $rateLimiter,
        MetricsCollector $collector,
    ): void {
        $endTime = microtime(true) + $phase->completion->seconds;
        $clientCount = count($clients);
        $i = 0;

        while (microtime(true) < $endTime) {
            $client = $clients[$i % $clientCount];
            $rateLimiter?->acquire();

            $cmd = $commandSelector->select();
            $result = CommandFactory::execute(
                $cmd->command, $client, $keyGenerator, $cmd->dataSizeBytes
            );
            $collector->record($result);
            $i++;
        }
    }

    private function log(string $message): void
    {
        $ts = date('H:i:s');
        fwrite(STDERR, "[{$ts}] {$message}\n");
    }
}
