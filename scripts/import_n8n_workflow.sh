#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/james/Document/Projects/CineCodex"
NODE_BIN="/Users/james/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin"

cd "$ROOT"
export PATH="$NODE_BIN:$PATH"
export N8N_USER_FOLDER="$ROOT/.n8n"

./node_modules/.bin/n8n import:workflow --input workflows/portal-video-generator-v2.1.json
./node_modules/.bin/n8n update:workflow --id=portal-video-generator-v2-1 --active=true
