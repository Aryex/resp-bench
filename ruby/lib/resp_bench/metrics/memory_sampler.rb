# frozen_string_literal: true

require "json"
require "fileutils"

module RespBench
  module Metrics
    # Samples process memory (RSS) and Ruby heap stats at regular intervals.
    # Streams each sample directly to an NDJSON file for real-time monitoring.
    #
    # On macOS, uses `ps` for RSS. On Linux, reads /proc/self/status.
    class MemorySampler
      SAMPLE_INTERVAL = 10 # seconds between samples (suitable for long soak tests)

      attr_reader :sample_count

      def initialize(driver_id:, connections:, phase_id:, output_path: nil)
        @driver_id = driver_id
        @connections = connections
        @phase_id = phase_id
        @output_path = output_path
        @thread = nil
        @stop = false
        @start_time = nil
        @sample_count = 0
        @file = nil
      end

      # Start sampling in background thread, streaming to file if path given
      def start
        @start_time = Time.now
        @stop = false

        if @output_path
          FileUtils.mkdir_p(File.dirname(@output_path))
          @file = File.open(@output_path, "a")
        end

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
        @file&.close
        @file = nil
      end

      # For backward compat: return sample count
      def samples
        @sample_count
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

        if @file
          @file.puts(JSON.generate(sample))
          @file.flush
        end

        @sample_count += 1
      end

      # Get current RSS in KB, cross-platform
      def current_rss_kb
        if File.exist?("/proc/self/status")
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
