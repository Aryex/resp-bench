/*
 * Copyright 2025 the original author or authors.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package io.valkey.javabenchmark.metrics;

import org.HdrHistogram.Histogram;
import org.HdrHistogram.HistogramLogWriter;
import org.HdrHistogram.Recorder;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.FileNotFoundException;
import java.io.FileOutputStream;
import java.io.PrintStream;
import java.nio.file.Path;
import java.util.Map;
import java.util.concurrent.*;

/**
 * Writes per-interval HDR histograms to an .hlog sidecar file.
 *
 * <p>Each command gets its own {@link Recorder} for lock-free concurrent recording.
 * A background thread periodically swaps the active histogram and writes the interval
 * to the log file using {@link HistogramLogWriter}.</p>
 *
 * <p>Thread safety: {@link Recorder#recordValue(long)} is safe for concurrent callers.
 * All other state is accessed only from the single scheduler thread.</p>
 *
 * @author Ilia Kolominsky
 */
public class IntervalHistogramLogger {
    private static final Logger logger = LoggerFactory.getLogger(IntervalHistogramLogger.class);

    /** Max trackable latency in microseconds (10 minutes), matching MetricsCollector. */
    private static final long MAX_LATENCY_MICROS = 600_000_000L;

    private final ConcurrentHashMap<String, Recorder> recorders = new ConcurrentHashMap<>();
    private final ConcurrentHashMap<String, Histogram> intervalHistograms = new ConcurrentHashMap<>();
    private ScheduledExecutorService scheduler;
    private HistogramLogWriter logWriter;
    private PrintStream printStream;
    private long baseTimeMs;

    /**
     * Start interval histogram logging.
     *
     * @param hlogPath        output .hlog file path
     * @param intervalSeconds  flush interval in seconds
     */
    public void start(Path hlogPath, int intervalSeconds) {
        try {
            printStream = new PrintStream(new FileOutputStream(hlogPath.toFile()));
        } catch (FileNotFoundException e) {
            throw new RuntimeException("Cannot create hlog file: " + hlogPath, e);
        }

        baseTimeMs = System.currentTimeMillis();
        logWriter = new HistogramLogWriter(printStream);
        logWriter.setBaseTime(baseTimeMs);
        logWriter.outputBaseTime(baseTimeMs);
        logWriter.outputLogFormatVersion();
        logWriter.outputLegend();

        scheduler = Executors.newSingleThreadScheduledExecutor(r -> {
            Thread t = new Thread(r, "interval-histogram-logger");
            t.setDaemon(true);
            return t;
        });
        scheduler.scheduleAtFixedRate(this::flush, intervalSeconds, intervalSeconds, TimeUnit.SECONDS);

        logger.info("Interval histogram logging started: interval={}s, file={}", intervalSeconds, hlogPath);
    }

    /**
     * Record a latency value for a command. Thread-safe.
     */
    public void recordValue(String commandName, long latencyMicros) {
        Recorder recorder = recorders.get(commandName);
        if (recorder == null) {
            recorder = recorders.computeIfAbsent(commandName,
                    k -> new Recorder(MAX_LATENCY_MICROS, 3));
        }
        recorder.recordValue(Math.min(latencyMicros, MAX_LATENCY_MICROS));
    }

    /**
     * Stop logging and flush any remaining data.
     */
    public void stop() {
        if (scheduler != null) {
            scheduler.shutdown();
            try {
                scheduler.awaitTermination(5, TimeUnit.SECONDS);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }
        // Final flush to capture the last partial interval
        flush();
        if (printStream != null) {
            printStream.close();
        }
        logger.info("Interval histogram logging stopped");
    }

    private void flush() {
        long now = System.currentTimeMillis();
        for (Map.Entry<String, Recorder> entry : recorders.entrySet()) {
            String tag = entry.getKey();
            Recorder recorder = entry.getValue();

            Histogram prev = intervalHistograms.get(tag);
            Histogram interval = recorder.getIntervalHistogram(prev);
            intervalHistograms.put(tag, interval);

            if (interval.getTotalCount() > 0) {
                interval.setTag(tag);
                double startSec = (interval.getStartTimeStamp() - baseTimeMs) / 1000.0;
                double endSec = (now - baseTimeMs) / 1000.0;
                logWriter.outputIntervalHistogram(startSec, endSec, interval);
            }
        }
    }
}
