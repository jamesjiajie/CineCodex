#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/james/Document/Projects/CineCodex"
PYTHON="/Users/james/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
HOST="${CINECODEX_HOST:-127.0.0.1}"
PORT="${CINECODEX_PORT:-8017}"

cd "$ROOT"
mkdir -p uploads/staging uploads/committed outputs/jobs logs

exec "$PYTHON" -m uvicorn portal.app:app --host "$HOST" --port "$PORT"
