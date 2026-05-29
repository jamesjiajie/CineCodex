#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/james/Document/Projects/CineCodex"
HOST="127.0.0.1"
PORT="8017"

cd "$ROOT"

clear
echo "Starting CineCodex Portal..."
echo

while lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; do
  PORT=$((PORT + 1))
done

echo "Portal URL:"
echo "http://$HOST:$PORT"
echo
echo "Keep this Terminal window open while using the portal."
echo "Press Control-C here to stop the portal."
echo

export CINECODEX_HOST="$HOST"
export CINECODEX_PORT="$PORT"

"$ROOT/scripts/start_portal.sh" &
SERVER_PID=$!

sleep 2
open "http://$HOST:$PORT" >/dev/null 2>&1 || true

wait "$SERVER_PID"
