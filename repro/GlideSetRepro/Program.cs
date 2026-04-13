using Valkey.Glide;

var mux = await ConnectionMultiplexer.ConnectAsync("localhost:6379");
var dbs = Enumerable.Range(0, 10).Select(_ => mux.GetDatabase()).ToArray();
Console.WriteLine("Connected 10 clients");

var value = new byte[512];
Random.Shared.NextBytes(value);
long ops = 0;
var cts = new CancellationTokenSource();
Console.CancelKeyPress += (_, e) => { e.Cancel = true; cts.Cancel(); };

var tasks = dbs.Select((db, i) => Task.Run(async () =>
{
    var rng = new Random(i);
    while (!cts.Token.IsCancellationRequested)
    {
        await db.StringSetAsync((ValkeyKey)$"k:{rng.Next(1_000_000)}", (ValkeyValue)value).ConfigureAwait(false);
        Interlocked.Increment(ref ops);
    }
})).ToArray();

Console.WriteLine("SET-only loop running. Ctrl+C to stop.");
while (!cts.Token.IsCancellationRequested)
{
    await Task.Delay(10_000, cts.Token).ContinueWith(_ => { });
    Console.WriteLine($"ops={Interlocked.Read(ref ops):N0}");
}

try { await Task.WhenAll(tasks); } catch { }
mux.Dispose();
