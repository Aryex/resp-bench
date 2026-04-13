#!/bin/bash
# Monitor RSS of a process on macOS. Usage: ./monitor-rss-macos.sh <PID> [interval_sec]
PID=${1:?Usage: $0 <PID> [interval_sec]}
INTERVAL=${2:-10}

echo "timestamp,rss_mb"
while kill -0 "$PID" 2>/dev/null; do
    RSS_MB=$(ps -o rss= -p "$PID" 2>/dev/null | awk '{printf "%.0f", $1/1024}')
    if [ -n "$RSS_MB" ]; then
        echo "$(date -u +%H:%M:%S),$RSS_MB"
    fi
    sleep "$INTERVAL"
done
echo "Process $PID exited"
