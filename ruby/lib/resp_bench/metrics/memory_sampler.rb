# frozen_string_literal: true

require "json"
require "fileutils"

module RespBench
  module Metrics
    # Samples process memory (RSS) and Ruby heap stats at regular intervals.
    # Designed to run in a background thread alongside the benchmark workload.
    #
    # Produces NDJSON output with one sample per line:
    #   {"t":0.5,"rss_kb":45000,"ruby_heap_live_slots":120000,"ruby_heap_free_slots":5000,...}
    #
    # On macOS, uses `Process.getrusage` for max RSS and /proc on Linux for current RSS.
    # Falls back to portable `ps` command if neither works.
    class MemorySampler
      SAMPLE_INTERVAL = 10 # seconds between samples (suitable for long soak tests)

      attr_reader :samples

      def initialize(driver_id:, connections:, phase_id:)
        @driver_id = driver_id
        @connections = connections
        @phase_id = phase_id
        @samples = []
        @thread = nil
        @stop = false
        @start_time = nil
      end

      # Start sampling in background thread
      def start
        @start_time = Time.now
        @stop = false
        # Take initial sample immediately
        take_sample
        @thread = Thread.new { sample_loop }
      end

      # Stop sampling, join background thread
      def stop
        @stop = true
        @thread&.join(2)
        # Take one final sample
        take_sample
      end

      # Write all samples to an NDJSON file
      def write_to(path)
        FileUtils.mkdir_p(File.dirname(path))
        File.open(path, "a") do |f|
          @samples.each do |sample|
            f.puts(JSON.generate(sample))
          end
        end
      end

      private

      def sample_loop
        until @stop
          sleep(SAMPLE_INTERVAL)
          take_sample unless @stop
        end
      end

      def take_sample
        elapsed = Time.now - @start_time
        gc = GC.stat

        sample = {
          t: elapsed.round(3),
          phase: @phase_id,
          driver_id: @driver_id,
          connections: @connections,
          pid: Process.pid,
          rss_kb: current_rss_kb,
          ruby_heap_live_slots: gc[:heap_live_slots],
          ruby_heap_free_slots: gc[:heap_free_slots],
          ruby_total_allocated_objects: gc[:total_allocated_objects],
          ruby_total_freed_objects: gc[:total_freed_objects],
          ruby_gc_count: gc[:count],
          ruby_malloc_increase_bytes: gc[:malloc_increase_bytes]
        }

        @samples << sample
      end

      # Get current RSS in KB, cross-platform
      def current_rss_kb
        if RUBY_PLATFORM.include?("darwin")
          # macOS: getrusage reports maxrss in bytes
          # But we want current RSS, not peak. Use ps for that.
          rss_from_ps
        elsif File.exist?("/proc/self/status")
          # Linux: read VmRSS from /proc
          rss_from_proc
        else
          rss_from_ps
        end
      end

      def rss_from_proc
        File.readlines("/proc/self/status").each do |line|
          if line.start_with?("VmRSS:")
            return line.split[1].to_i # already in kB
          end
        end
        0
      rescue StandardError
        0
      end

      def rss_from_ps
        `ps -o rss= -p #{Process.pid}`.strip.to_i
      rescue StandardError
        0
      end
    end
  end
end
