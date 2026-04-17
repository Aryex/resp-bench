<?php

declare(strict_types=1);

namespace RespBench\Metrics;

/**
 * Writes benchmark metrics to NDJSON format (Newline Delimited JSON).
 */
class NdjsonWriter
{
    private ?string $commitId = null;
    private ?string $driverId = null;
    private ?string $primaryDriverVersion = null;
    private ?string $secondaryDriverId = null;
    private ?string $secondaryDriverVersion = null;

    public function __construct(private readonly string $outputPath) {}

    public function setMetadata(
        ?string $commitId,
        ?string $driverId,
        ?string $primaryDriverVersion,
        ?string $secondaryDriverId = null,
        ?string $secondaryDriverVersion = null,
    ): void {
        $this->commitId = $commitId;
        $this->driverId = $driverId;
        $this->primaryDriverVersion = $primaryDriverVersion;
        $this->secondaryDriverId = $secondaryDriverId;
        $this->secondaryDriverVersion = $secondaryDriverVersion;
    }

    public function writePhaseResults(
        string $phaseId,
        string $status,
        int $connections,
        MetricsCollector $collector,
    ): void {
        $dir = dirname($this->outputPath);
        if (!is_dir($dir)) {
            mkdir($dir, 0755, true);
        }

        $json = $this->buildPhaseJson($phaseId, $status, $connections, $collector);
        file_put_contents($this->outputPath, json_encode($json, JSON_THROW_ON_ERROR) . "\n", FILE_APPEND);
    }

    private function buildPhaseJson(
        string $phaseId,
        string $status,
        int $connections,
        MetricsCollector $collector,
    ): array {
        $result = [];

        // Metadata
        if ($this->commitId || $this->driverId) {
            $metadata = [];
            if ($this->commitId) $metadata['commit_id'] = $this->commitId;
            $metadata['timestamp'] = gmdate('Y-m-d\TH:i:s\Z');
            if ($this->driverId) $metadata['driver_id'] = $this->driverId;
            if ($this->primaryDriverVersion) $metadata['primary_driver_version'] = $this->primaryDriverVersion;
            if ($this->secondaryDriverId) $metadata['secondary_driver_id'] = $this->secondaryDriverId;
            if ($this->secondaryDriverVersion) $metadata['secondary_driver_version'] = $this->secondaryDriverVersion;
            $result['metadata'] = $metadata;
        }

        // Phase info
        $result['phase'] = [
            'id' => $phaseId,
            'status' => $status,
            'start_timestamp' => $collector->startTimeIso(),
            'finish_timestamp' => $collector->endTimeIso(),
            'duration_ms' => $collector->durationMillis(),
            'connections' => $connections,
        ];

        // Totals
        $result['totals'] = [
            'requests' => $collector->totalRequests(),
            'errors' => $collector->totalErrors(),
        ];

        // Per-command metrics
        $metrics = [];
        foreach ($collector->allMetrics() as $cmdName => $cmdMetrics) {
            $metrics[$cmdName] = [
                'requests' => $cmdMetrics->requests,
                'errors' => $cmdMetrics->errors,
                'latency' => [
                    'unit' => 'us',
                    'count' => $cmdMetrics->count(),
                    'summary' => [
                        'min' => $cmdMetrics->min(),
                        'p50' => $cmdMetrics->percentile(50),
                        'p95' => $cmdMetrics->percentile(95),
                        'p99' => $cmdMetrics->percentile(99),
                        'p999' => $cmdMetrics->percentile(99.9),
                        'max' => $cmdMetrics->max(),
                    ],
                ],
            ];
        }
        $result['metrics'] = $metrics;

        return $result;
    }
}
