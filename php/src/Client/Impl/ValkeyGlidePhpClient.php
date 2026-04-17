<?php

declare(strict_types=1);

namespace RespBench\Client\Impl;

use RespBench\Client\BenchmarkClient;
use RespBench\Client\TimedResult;
use RespBench\Config\DriverConfig;

/**
 * Benchmark client implementation using the valkey-glide PHP extension.
 */
class ValkeyGlidePhpClient extends BenchmarkClient
{
    private ?\ValkeyGlide $client = null;

    public function connect(string $host, int $port, DriverConfig $config): void
    {
        $this->client = new \ValkeyGlide();

        $addresses = [['host' => $host, 'port' => $port]];
        $useTls = isset($config->tls);
        $credentials = null;
        if ($config->auth) {
            $credentials = [];
            if (isset($config->auth['password'])) {
                $credentials['password'] = $config->auth['password'];
            }
            if (isset($config->auth['username'])) {
                $credentials['username'] = $config->auth['username'];
            }
        }

        $this->client->connect(
            addresses: $addresses,
            use_tls: $useTls,
            credentials: $credentials,
            request_timeout: 5000,
        );
    }

    public function connected(): bool
    {
        if (!$this->client) {
            return false;
        }
        try {
            return $this->client->ping() === 'PONG';
        } catch (\Throwable) {
            return false;
        }
    }

    public function ping(): TimedResult
    {
        return $this->measure(fn() => $this->client->ping());
    }

    public function get(string $key): TimedResult
    {
        return $this->measure(fn() => $this->client->get($key));
    }

    public function set(string $key, string $value): TimedResult
    {
        return $this->measure(fn() => $this->client->set($key, $value));
    }

    public function del(string $key): TimedResult
    {
        return $this->measure(fn() => $this->client->del($key));
    }

    public function close(): void
    {
        $this->client?->close();
        $this->client = null;
    }

    public function driverVersion(): string
    {
        return phpversion('valkey_glide') ?: 'unknown';
    }
}
