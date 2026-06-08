#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/james/Document/Projects/CineCodex"
BOOTSTRAP_PYTHON="${CINECODEX_BOOTSTRAP_PYTHON:-/usr/bin/python3}"
VENV="$ROOT/.venv"
PYTHON="${CINECODEX_PYTHON:-$VENV/bin/python}"
HOST="${CINECODEX_HOST:-127.0.0.1}"
PORT="${CINECODEX_PORT:-8017}"

cd "$ROOT"
mkdir -p uploads/staging uploads/committed outputs/jobs logs

if [[ ! -x "$PYTHON" ]]; then
  echo "Creating local Python environment..."
  "$BOOTSTRAP_PYTHON" -m venv "$VENV"
fi

if ! "$PYTHON" - <<'PY' >/dev/null 2>&1
import importlib.util
missing = [
    name for name in ("fastapi", "uvicorn", "multipart", "PIL", "edge_tts")
    if importlib.util.find_spec(name) is None
]
raise SystemExit(1 if missing else 0)
PY
then
  echo "Installing CineCodex portal dependencies..."
  if ! "$PYTHON" -m pip install --upgrade pip; then
    echo
    echo "Failed to upgrade pip. Check your network connection and try again."
    exit 1
  fi
  if ! "$PYTHON" -m pip install -r "$ROOT/requirements.txt"; then
    echo
    echo "Failed to install CineCodex portal dependencies."
    echo "Run this command from the project folder after network access is available:"
    echo "  .venv/bin/python -m pip install -r requirements.txt"
    exit 1
  fi
fi

exec "$PYTHON" -m uvicorn portal.app:app --host "$HOST" --port "$PORT"
