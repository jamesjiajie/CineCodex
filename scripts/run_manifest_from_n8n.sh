#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/james/Document/Projects/CineCodex"
PYTHON="/Users/james/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
INPUT="${1:-}"

if [[ -z "$INPUT" ]]; then
  echo "Missing manifest path" >&2
  exit 2
fi

BASENAME="$(basename "$INPUT")"
if [[ "$BASENAME" != "manifest.json" ]]; then
  echo "Ignored non-manifest file: $INPUT"
  exit 0
fi

if [[ ! -f "$INPUT" ]]; then
  echo "Manifest does not exist: $INPUT" >&2
  exit 3
fi

cd "$ROOT"
"$PYTHON" scripts/run_video_job.py --manifest "$INPUT"
