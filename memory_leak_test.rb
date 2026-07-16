#!/usr/bin/env ruby
# frozen_string_literal: true

# Minimal memory leak reproduction test for valkey-glide-ruby.
# Runs GET/SET in a tight loop for 60s, sampling RSS every second.
# No resp-bench dependencies — just the valkey gem directly.
#
# Usage:
#   bundle exec ruby memory_leak_test.rb [host] [port] [duration_secs]
#
# Requires a running Valkey/Redis server.

require "valkey"
require "json"

HOST = ARGV[0] || "localhost"
PORT = (ARGV[1] || 6379).to_i
DURATION = (ARGV[2] || 60).to_i
KEY_COUNT = 1000
VALUE_SIZE = 512
SAMPLE_INTERVAL = 1.0

def current_rss_kb
  `ps -o rss= -p #{Process.pid}`.strip.to_i
end

def run_test(driver_name, &connect_block)
  puts "=" * 60
  puts "Driver: #{driver_name}"
  puts "Server: #{HOST}:#{PORT}, Duration: #{DURATION}s"
  puts "Workload: 80% GET / 20% SET, #{KEY_COUNT} keys, #{VALUE_SIZE}B values"
  puts "=" * 60

  client = connect_block.call

  # Warmup: populate keys
  KEY_COUNT.times do |i|
    client.set("leak:#{i}", "x" * VALUE_SIZE)
  end
  puts "Warmup done (#{KEY_COUNT} keys populated)"

  # Force GC before measurement
  GC.start
  GC.compact if GC.respond_to?(:compact)
  sleep 0.1

  samples = []
  start_time = Time.now
  request_count = 0
  rng = Random.new(12345)

  # Background sampler
  stop = false
  sampler = Thread.new do
    until stop
      elapsed = Time.now - start_time
      rss = current_rss_kb
      gc = GC.stat
      samples << {
        t: elapsed.round(2),
        rss_kb: rss,
        rss_mb: (rss / 1024.0).round(1),
        heap_live_slots: gc[:heap_live_slots],
        heap_memory_mb: (gc[:heap_live_slots] * 40 / 1024.0 / 1024.0).round(2),
        malloc_increase_mb: (gc[:malloc_increase_bytes] / 1024.0 / 1024.0).round(2),
        ruby_memory_mb: ((gc[:heap_live_slots] * 40 + gc[:malloc_increase_bytes]) / 1024.0 / 1024.0).round(2),
        gc_count: gc[:count],
        total_allocated: gc[:total_allocated_objects],
        total_freed: gc[:total_freed_objects]
      }
      sleep SAMPLE_INTERVAL
    end
  end

  # Main request loop
  end_time = start_time + DURATION
  while Time.now < end_time
    key = "leak:#{rng.rand(KEY_COUNT)}"
    if rng.rand < 0.8
      client.get(key)
    else
      client.set(key, "x" * VALUE_SIZE)
    end
    request_count += 1
  end

  stop = true
  sampler.join(2)

  # Final sample
  final_rss = current_rss_kb
  elapsed = Time.now - start_time

  client.close

  # Report
  puts "\nResults:"
  puts "  Requests: #{request_count} (#{(request_count / elapsed).round(0)} req/s)"
  puts "  Duration: #{elapsed.round(1)}s"
  puts ""
  puts "  RSS start:  #{samples.first[:rss_mb]} MB"
  puts "  RSS end:    #{(final_rss / 1024.0).round(1)} MB"
  puts "  RSS growth: #{((final_rss - samples.first[:rss_kb]) / 1024.0).round(1)} MB"
  puts ""
  puts "  Heap start: #{samples.first[:heap_live_slots]} slots"
  puts "  Heap end:   #{GC.stat[:heap_live_slots]} slots"
  puts "  Heap growth: #{GC.stat[:heap_live_slots] - samples.first[:heap_live_slots]} slots"
  puts ""

  # Check for leak trend (compare first 5s avg vs last 5s avg)
  early = samples.select { |s| s[:t] < 5 }
  late = samples.select { |s| s[:t] > (DURATION - 5) }
  if early.any? && late.any?
    early_avg = early.sum { |s| s[:rss_kb] } / early.size / 1024.0
    late_avg = late.sum { |s| s[:rss_kb] } / late.size / 1024.0
    rate = (late_avg - early_avg) / (late.last[:t] - early.first[:t])
    puts "  Leak rate: #{rate.round(3)} MB/s (#{(rate * 60).round(1)} MB/min)"
    if rate > 0.1
      puts "  ⚠️  PROBABLE MEMORY LEAK DETECTED"
    else
      puts "  ✅ Memory appears stable"
    end
  end

  puts ""

  # Write samples to file
  outfile = "memory_leak_#{driver_name}.ndjson"
  File.open(outfile, "w") do |f|
    samples.each { |s| f.puts(JSON.generate(s)) }
  end
  puts "Samples written to: #{outfile}"
  puts ""
end

# --- Run valkey-glide-ruby ---
run_test("valkey-glide-ruby") do
  Valkey.new(host: HOST, port: PORT)
end
