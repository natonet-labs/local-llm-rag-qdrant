#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"   # if run_api_server.sh lives in project root

cd "$PROJECT_DIR"

# Activate venv
source .venv/bin/activate

exec python -m uvicorn api_server:app --host 0.0.0.0 --port 8000
