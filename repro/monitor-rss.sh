#!/bin/bash
# Monitor total RSS of a process and its children. Usage: ./monitor-rss.sh <PID> [interval_sec]
PID=${1:?Usage: $0 <PID> [interval_sec]}
INTERVAL=${2:-10}

echo "timestamp,rss_mb"
while kill -0 "$PID" 2>/dev/null; do
    RSS_KB=$(awk '/VmRSS/{print $2}' /proc/$PID/status 2>/dev/null)
    if [ -n "$RSS_KB" ]; then
        echo "$(date -u +%H:%M:%S),$((RSS_KB / 1024))"
    fi
    sleep "$INTERVAL"
done
echo "Process $PID exited"
