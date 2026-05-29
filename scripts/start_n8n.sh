#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/james/Document/Projects/CineCodex"
NODE_BIN="/Users/james/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin"

cd "$ROOT"
mkdir -p logs uploads/staging uploads/committed outputs/jobs

export PATH="$NODE_BIN:$PATH"
export N8N_USER_FOLDER="$ROOT/.n8n"
export N8N_PORT="${N8N_PORT:-5678}"
export N8N_HOST="${N8N_HOST:-127.0.0.1}"
export N8N_SECURE_COOKIE=false

exec ./node_modules/.bin/n8n start
