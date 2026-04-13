#!/bin/bash
# Run a repro project with RSS monitoring. Usage: ./run.sh <project_dir> [duration_min]
set -e
PROJECT=${1:?Usage: $0 <GlideSetRepro|GlideGetRepro> [duration_min]}
DURATION=${2:-5}
DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Building $PROJECT ==="
dotnet build "$DIR/$PROJECT" -c Release -v q

echo "=== Starting server ==="
"$DIR/start-server.sh"
sleep 1
valkey-cli FLUSHALL > /dev/null 2>&1 || redis-cli FLUSHALL > /dev/null 2>&1 || true

echo "=== Running $PROJECT for ${DURATION}m ==="
dotnet run --project "$DIR/$PROJECT" -c Release &
PID=$!

echo "=== Monitoring RSS (PID=$PID) ==="
if [[ "$(uname)" == "Darwin" ]]; then
    "$DIR/monitor-rss-macos.sh" $PID 10 &
else
    "$DIR/monitor-rss.sh" $PID 10 &
fi
MON_PID=$!

sleep $((DURATION * 60))
kill $PID 2>/dev/null || true
wait $PID 2>/dev/null || true
kill $MON_PID 2>/dev/null || true

echo "=== Done ==="
