# frozen_string_literal: true

require "json"
require "fileutils"
require "concurrent"

module RespBench
  module Metrics
    # Samples process memory (RSS), Ruby heap stats, throughput, and latency at regular intervals.
    # Streams each sample directly to an NDJSON file for real-time monitoring.
    class MemorySampler
      SAMPLE_INTERVAL = 10 # seconds between samples

      attr_reader :sample_count
      attr_accessor :request_counter, :latency_sum_us, :metrics_collector

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
        @request_counter = Concurrent::AtomicFixnum.new(0)
        @latency_sum_us = Concurrent::AtomicFixnum.new(0)
        @metrics_collector = nil
        @prev_requests = 0
        @prev_latency_sum = 0
        @prev_time = nil
      end

      def start
        @start_time = Time.now
        @prev_time = @start_time
        @stop = false

        if @output_path
          FileUtils.mkdir_p(File.dirname(@output_path))
          @file = File.open(@output_path, "a")
        end

        take_sample
        @thread = Thread.new { sample_loop }
      end

      def stop
        @stop = true
        @thread&.join(2)
        take_sample
        @file&.close
        @file = nil
      end

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
        now = Time.now
        elapsed = now - @start_time
        gc = GC.stat

        current_requests = @request_counter.value
        current_latency_sum = @latency_sum_us.value
        dt = now - @prev_time
        interval_reqs = current_requests - @prev_requests
        rps = dt > 0 ? (interval_reqs / dt).round(0) : 0
        avg_latency_us = interval_reqs > 0 ? ((current_latency_sum - @prev_latency_sum) / interval_reqs) : 0

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
          ruby_malloc_increase_bytes: gc[:malloc_increase_bytes],
          requests_total: current_requests,
          rps: rps,
          avg_latency_us: avg_latency_us
        }

        # Snapshot latency percentiles from the metrics collector if available
        if @metrics_collector
          @metrics_collector.all_metrics.each do |cmd_name, cmd_metrics|
            next unless cmd_metrics.count > 0
            sample[:"#{cmd_name.downcase}_p50_us"] = cmd_metrics.p50.to_i
            sample[:"#{cmd_name.downcase}_p99_us"] = cmd_metrics.p99.to_i
          end
        end

        @prev_requests = current_requests
        @prev_latency_sum = current_latency_sum
        @prev_time = now

        if @file
          @file.puts(JSON.generate(sample))
          @file.flush
        end

        @sample_count += 1
      end

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
            return line.split[1].to_i
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
