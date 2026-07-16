#!/usr/bin/env ruby
# frozen_string_literal: true

# Isolate memory leak: GET-only vs SET-only for valkey-glide-ruby.
#
# Usage:
#   bundle exec ruby memory_leak_isolate_commands.rb [host] [port] [duration_secs]

require "valkey"
require "json"

HOST = ARGV[0] || "localhost"
PORT = (ARGV[1] || 6379).to_i
DURATION = (ARGV[2] || 30).to_i
KEY_COUNT = 1000
VALUE_SIZE = 512
SAMPLE_INTERVAL = 0.5

def current_rss_kb
  `ps -o rss= -p #{Process.pid}`.strip.to_i
end

def run_command_test(command_name)
  puts "=" * 60
  puts "Test: #{command_name}-only | Duration: #{DURATION}s"
  puts "=" * 60

  client = Valkey.new(host: HOST, port: PORT)

  # Populate keys first
  KEY_COUNT.times { |i| client.set("iso:#{i}", "x" * VALUE_SIZE) }
  puts "Keys populated"

  GC.start
  GC.compact if GC.respond_to?(:compact)
  sleep 0.1

  samples = []
  start_time = Time.now
  request_count = 0
  rng = Random.new(12345)

  stop = false
  sampler = Thread.new do
    until stop
      elapsed = Time.now - start_time
      rss = current_rss_kb
      gc = GC.stat
      ruby_mem = (gc[:heap_live_slots] * 40 + gc[:malloc_increase_bytes]) / 1024.0 / 1024.0
      samples << {
        t: elapsed.round(2),
        rss_mb: (rss / 1024.0).round(1),
        ruby_memory_mb: ruby_mem.round(2),
        core_memory_mb: ((rss / 1024.0) - ruby_mem).round(2)
      }
      sleep SAMPLE_INTERVAL
    end
  end

  end_time = start_time + DURATION
  while Time.now < end_time
    key = "iso:#{rng.rand(KEY_COUNT)}"
    case command_name
    when "GET"
      client.get(key)
    when "SET"
      client.set(key, "x" * VALUE_SIZE)
    end
    request_count += 1
  end

  stop = true
  sampler.join(2)

  client.close
  elapsed = Time.now - start_time

  rss_start = samples.first[:rss_mb]
  rss_end = samples.last[:rss_mb]
  core_start = samples.first[:core_memory_mb]
  core_end = samples.last[:core_memory_mb]
  leak_rate = (rss_end - rss_start) / elapsed

  puts "  Requests: #{request_count} (#{(request_count / elapsed).round(0)} req/s)"
  puts "  RSS: #{rss_start} MB -> #{rss_end} MB (#{rss_end - rss_start > 0 ? '+' : ''}#{(rss_end - rss_start).round(1)} MB)"
  puts "  Core: #{core_start} MB -> #{core_end} MB (#{core_end - core_start > 0 ? '+' : ''}#{(core_end - core_start).round(1)} MB)"
  puts "  Leak rate: #{leak_rate.round(3)} MB/s"
  if leak_rate > 0.1
    puts "  ⚠️  LEAK DETECTED"
  else
    puts "  ✅ Stable"
  end
  puts ""

  # Write samples
  outfile = "memory_leak_glide_#{command_name.downcase}_only.ndjson"
  File.open(outfile, "w") do |f|
    samples.each { |s| f.puts(JSON.generate(s.merge(command: command_name))) }
  end

  { command: command_name, samples: samples, leak_rate: leak_rate,
    rss_start: rss_start, rss_end: rss_end, core_start: core_start, core_end: core_end }
end

# Run both tests
results = []
results << run_command_test("GET")
results << run_command_test("SET")

puts "=" * 60
puts "Summary:"
puts "  GET-only leak rate: #{results[0][:leak_rate].round(3)} MB/s"
puts "  SET-only leak rate: #{results[1][:leak_rate].round(3)} MB/s"
puts "=" * 60
