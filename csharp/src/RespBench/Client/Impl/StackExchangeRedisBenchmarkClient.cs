/*
 * Copyright 2025 the original author or authors.
 */
using System.Diagnostics;
using System.Reflection;
using RespBench.Config;
using StackExchange.Redis;

namespace RespBench.Client.Impl;

/// <summary>
/// StackExchange.Redis implementation of IBenchmarkClient.
/// </summary>
public class StackExchangeRedisBenchmarkClient : IBenchmarkClient
{
    private ConnectionMultiplexer? _connection;
    private IDatabase? _db;
    private volatile bool _connected;

    public string DriverId => "stackexchange-redis";
    public string Description => "StackExchange.Redis client";
    public bool IsConnected => _connected;

    public string DriverVersion
    {
        get
        {
            try
            {
                var asm = typeof(ConnectionMultiplexer).Assembly;
                return asm.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion
                    ?? asm.GetName().Version?.ToString() ?? "unknown";
            }
            catch { return "unknown"; }
        }
    }

    public void Connect(string host, int port, DriverConfig driverConfig)
    {
        var options = new ConfigurationOptions
        {
            EndPoints = { { host, port } },
            AbortOnConnectFail = true,
            ConnectRetry = 3,
            ConnectTimeout = 10000,
            AllowAdmin = true, // For FlushDb
        };

        // Configure TLS
        if (driverConfig.IsTlsEnabled)
        {
            options.Ssl = true;
            options.SslProtocols = System.Security.Authentication.SslProtocols.Tls12 | System.Security.Authentication.SslProtocols.Tls13;
        }

        // Configure authentication
        if (driverConfig.HasAuth)
        {
            if (!string.IsNullOrEmpty(driverConfig.Auth?.Username))
                options.User = driverConfig.Auth.Username;
            options.Password = driverConfig.Auth!.Password;
        }

        // Configure command timeout
        if (driverConfig.CommandTimeoutMs.HasValue)
        {
            options.SyncTimeout = driverConfig.CommandTimeoutMs.Value;
            options.AsyncTimeout = driverConfig.CommandTimeoutMs.Value;
        }

        // Apply specific driver config
        if (driverConfig.SpecificDriverConfig != null)
        {
            // StackExchange.Redis specific options can be added here
            // e.g., sync_timeout, async_timeout, etc.
        }

        _connection = ConnectionMultiplexer.Connect(options);
        _db = _connection.GetDatabase();

        // Test connection
        var pong = _db.Ping();
        if (pong.TotalMilliseconds <= 0 && pong.TotalMilliseconds > 30000)
            throw new ClientException("Connection test failed");

        _connected = true;
    }

    public async Task<TimedResult<object?>> Set(byte[] key, byte[] value)
    {
        long start = Stopwatch.GetTimestamp();
        await _db!.StringSetAsync((RedisKey)key, (RedisValue)value).ConfigureAwait(false);
        long latencyMicros = GetElapsedMicros(start);
        return TimedResult<object?>.OfVoid(latencyMicros);
    }

    public async Task<TimedResult<byte[]?>> Get(byte[] key)
    {
        long start = Stopwatch.GetTimestamp();
        RedisValue result = await _db!.StringGetAsync((RedisKey)key).ConfigureAwait(false);
        long latencyMicros = GetElapsedMicros(start);
        byte[]? value = result.IsNullOrEmpty ? null : (byte[])result!;
        return TimedResult<byte[]?>.Of(value, latencyMicros);
    }

    public async Task<TimedResult<string?>> Ping()
    {
        long start = Stopwatch.GetTimestamp();
        await _db!.PingAsync().ConfigureAwait(false);
        long latencyMicros = GetElapsedMicros(start);
        return TimedResult<string?>.Of("PONG", latencyMicros);
    }

    public Task<TimedResult<string?>> Ping(byte[] message)
    {
        return Ping(); // StackExchange.Redis Ping doesn't support message
    }

    public async Task<TimedResult<long>> Del(params byte[][] keys)
    {
        long start = Stopwatch.GetTimestamp();
        var redisKeys = keys.Select(k => (RedisKey)k).ToArray();
        long count = await _db!.KeyDeleteAsync(redisKeys).ConfigureAwait(false);
        long latencyMicros = GetElapsedMicros(start);
        return TimedResult<long>.Of(count, latencyMicros);
    }

    public async Task<TimedResult<object?>> FlushDb()
    {
        long start = Stopwatch.GetTimestamp();
        var server = _connection!.GetServer(_connection.GetEndPoints()[0]);
        await server.FlushDatabaseAsync().ConfigureAwait(false);
        long latencyMicros = GetElapsedMicros(start);
        return TimedResult<object?>.OfVoid(latencyMicros);
    }

    public void Dispose()
    {
        _connected = false;
        _connection?.Dispose();
        _connection = null;
        _db = null;
    }

    private static long GetElapsedMicros(long startTimestamp)
    {
        long elapsed = Stopwatch.GetTimestamp() - startTimestamp;
        return elapsed * 1_000_000 / Stopwatch.Frequency;
    }
}
