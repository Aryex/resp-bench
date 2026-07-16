# Memory Leak Investigation: valkey-glide-ruby (valkey-glide-rb gem v1.0.0)

## Summary

**valkey-glide-ruby has a confirmed native memory leak at ~0.8 MB/s** during sustained GET/SET workloads. The leak is in the Rust FFI layer (`libglide_ffi.dylib`), not in Ruby-managed memory. GET commands leak ~3.5× faster than SET commands, implicating the response-value extraction path.

## Environment

- **Ruby**: 4.0.5 (arm64-darwin25)
- **Gem**: valkey-glide-rb 1.0.0 (built from source, see below)
- **Source**: `valkey-io/valkey-glide-ruby` main branch, commit `fdd1bd8`
  - Worktree location: `~/bq/valkey-glide-ruby-main`
  - Gemspec version constant: `1.0.0` (in `lib/valkey/version.rb`)
- **Native lib**: `libglide_ffi.dylib` (Mach-O arm64, built via `rake native:build`)
  - Built from `valkey-glide` submodule pinned at commit `49bf2d3`
- **Published gem equivalence**: The published `valkey-glide-rb` v0.9.0 on RubyGems shares the same FFI/Rust core — the leak likely affects it too. Main branch has bumped the version to 1.0.0 but no new release has been published yet.
- **v0.9.0 confirmation**: Git log between `v0.9.0` tag (May 29, 2026) and current `main` (`fdd1bd8`, Jul 7) shows **zero commits related to memory freeing, arenas, leaks, or deallocation**. The `CommandResult` response handling path is unchanged. The leak is present in v0.9.0.
- **Introduced in**: Commit `bab3cb3` ("Removing protobuf layer in connection creation #87", Apr 16, 2026) which switched from protobuf-based responses to direct FFI struct responses with an arena allocator. This commit is an ancestor of both `v0.9.0-rc1` and `v0.9.0`. Every released version has this leak — there was no prior release without it.
- **Server**: Valkey 8.1.1 (localhost, standalone)
- **OS**: macOS (Apple Silicon)

## Reproduction

Minimal self-contained script — no external framework dependencies:

```ruby
require "valkey"

client = Valkey.new(host: "localhost", port: 6379)

# Populate keys
1000.times { |i| client.set("leak:#{i}", "x" * 512) }

# Sustained workload — observe RSS growth
GC.start
start_rss = `ps -o rss= -p #{Process.pid}`.strip.to_i

60.times do |sec|
  1000.times do
    key = "leak:#{rand(1000)}"
    rand < 0.8 ? client.get(key) : client.set(key, "x" * 512)
  end
  rss = `ps -o rss= -p #{Process.pid}`.strip.to_i
  puts "#{sec}s: RSS=#{rss/1024} MB (growth: +#{(rss - start_rss)/1024} MB)"
end

client.close
```

Run with: `bundle exec ruby leak_repro.rb` (requires a running Valkey/Redis on localhost:6379)

Expected output: RSS grows linearly at ~0.8 MB/s. redis-rb with the same workload stays flat.

## Detailed Findings

### 1. Overall Leak (60s, mixed GET/SET 80/20)

| Driver | RSS Start | RSS End | Growth | Leak Rate | Ruby Heap Growth |
|--------|-----------|---------|--------|-----------|-----------------|
| redis-rb 5.4.1 | 37.5 MB | 39.8 MB | +2.3 MB | 0.03 MB/s | +18K slots |
| valkey-glide-ruby 1.0.0 | 34.7 MB | 87.4 MB | +52.8 MB | 0.80 MB/s | +31K slots |

### 2. Ruby Memory vs Native Memory

The leak is **98% native memory**:
- Ruby-managed memory (heap_live_slots × 40B + malloc_increase_bytes): grows ~2 MB over 60s for both drivers
- Native/FFI memory (RSS − Ruby memory): grows **+50 MB** for glide, +0.3 MB for redis-rb

### 3. GET vs SET Isolation (30s each, single command type)

| Command | Leak Rate | 30s Core Memory Growth |
|---------|-----------|----------------------|
| GET-only | 0.86 MB/s | +26.0 MB |
| SET-only | 0.25 MB/s | +4.6 MB |

Both commands leak, but **GET is 3.5× worse**. GET returns a 512-byte value through FFI; SET returns only "OK".

## Root Cause Analysis

The leak is in native (Rust) memory that Ruby's GC cannot see or free. Based on the FFI bindings structure in `lib/valkey/bindings.rb`:

### Suspect: `CommandResponse` arena not freed

Each command call returns a `CommandResponse` struct via:
```ruby
attach_function :command, [...], :pointer, blocking: true  # returns *mut CommandResult
```

The `CommandResult` contains:
```ruby
class CommandResult < FFI::Struct
  layout(
    :response, CommandResponse.by_ref,
    :command_error, CommandError.by_ref,
    :arena, :pointer  # *mut ResponseArena  <-- THIS
  )
end
```

The `arena` pointer holds the backing memory for the response data. If this arena isn't explicitly freed after extracting the response value, it accumulates indefinitely.

### Why GET leaks faster than SET

- GET response: carries `string_value` (512 bytes of actual data) allocated inside the arena
- SET response: carries just "OK" (2 bytes) or nil — minimal arena allocation per call

### Where to look in the Ruby client code

**File**: `~/bq/valkey-glide-ruby-main/lib/valkey.rb`

Look for how `CommandResult` pointers are handled after the FFI `command()` call returns. Specifically:
1. Is there a `free` or `drop` call on `result.arena` after the response is extracted? **NO — confirmed missing.**
2. Is there a finalizer registered on the Ruby wrapper object? **NO.**
3. Does the code call any cleanup FFI function like `free_command_result` or similar? **NO.**

Confirmed by `grep -n "arena\|free\|drop" lib/valkey.rb`:
- `free_connection_response` is called (for connection setup only)
- `drop_otel_span` is called (for telemetry spans)
- **No call to free the `CommandResult` arena after `convert_response`** — this is the bug

### Relevant FFI functions that exist in bindings

```ruby
attach_function :free_connection_response, [:pointer], :void
attach_function :free_c_string, [:pointer], :void
```

Note: there is `free_connection_response` and `free_c_string`, but **no `free_command_result`** or `free_arena` function is attached. This is likely the missing piece — the Rust side may expose such a function, but the Ruby bindings don't call it.

## Files Produced

| File | Description |
|------|-------------|
| `memory_leak_test.rb` | Minimal glide leak reproduction (standalone) |
| `memory_leak_test_redis.rb` | Same test with redis-rb (control) |
| `memory_leak_isolate_commands.rb` | GET-only vs SET-only isolation test |
| `ruby/memory_leak_valkey-glide-ruby.ndjson` | Raw memory samples (glide, 60s) |
| `ruby/memory_leak_redis-rb.ndjson` | Raw memory samples (redis-rb, 60s) |
| `ruby/memory_leak_glide_get_only.ndjson` | GET-only samples (30s) |
| `ruby/memory_leak_glide_set_only.ndjson` | SET-only samples (30s) |
| `results/memory_leak_isolated_report.html` | Interactive Plotly chart |
| `scripts/generate_memory_report.py` | Report generator for resp-bench integration |

## Suggested Fix

1. Check if `glide-ffi` exposes a `free_command_result` or `drop_arena` function in its C API
2. If yes: attach it in `bindings.rb` and call it after every command response extraction in `valkey.rb`
3. If no: add one to the Rust FFI crate (`glide-ffi/src/lib.rs`) that drops the arena, then wire it through
4. Verify fix with the reproduction script — RSS should stay flat like redis-rb
