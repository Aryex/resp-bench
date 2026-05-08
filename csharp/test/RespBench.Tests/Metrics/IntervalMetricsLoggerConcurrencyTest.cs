using System.Text.Json;
using RespBench.Metrics;
using Xunit;

namespace RespBench.Tests.Metrics;

public class IntervalMetricsLoggerConcurrencyTest
{
    [Fact]
    public async Task Flush_UnderConcurrentWrites_DoesNotThrow()
    {
        var logger = new IntervalMetricsLogger();
        var tmpFile = Path.GetTempFileName();
        logger.Start(tmpFile, "TEST", intervalSeconds: 1);

        var cts = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        var workers = Enumerable.Range(0, 8).Select(_ => Task.Run(() =>
        {
            var rng = new Random();
            while (!cts.IsCancellationRequested)
            {
                logger.RecordValue("GET", rng.Next(1, 10000), true);
            }
        })).ToArray();

        await Task.WhenAll(workers);
        logger.Stop();

        var lines = File.ReadAllLines(tmpFile).Where(l => !string.IsNullOrEmpty(l)).ToArray();
        Assert.NotEmpty(lines);
        foreach (var line in lines)
        {
            JsonDocument.Parse(line); // throws if invalid JSON
        }
        File.Delete(tmpFile);
    }
}
