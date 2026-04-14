#!/bin/bash
# Periodically capture GC heap snapshots. Usage: ./capture-gcdumps.sh <PID> <output_dir> [interval_min]
PID=${1:?Usage: $0 <PID> <output_dir> [interval_min]}
OUTPUT_DIR=${2:?Usage: $0 <PID> <output_dir> [interval_min]}
INTERVAL=${3:-30}

mkdir -p "$OUTPUT_DIR"
echo "Capturing gcdumps for PID=$PID every ${INTERVAL}m to $OUTPUT_DIR"

while kill -0 "$PID" 2>/dev/null; do
    TS=$(date -u +%Y%m%dT%H%M%SZ)
    FILE="$OUTPUT_DIR/heap-$TS.gcdump"
    echo "[$TS] Capturing snapshot..."
    dotnet-gcdump collect -p "$PID" -o "$FILE" 2>&1 && echo "[$TS] Saved $FILE ($(du -h "$FILE" | cut -f1))" || echo "[$TS] Failed"
    sleep $((INTERVAL * 60))
done
echo "Process $PID exited"
