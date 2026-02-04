#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/Users/nvo/projects/llm-rag"
cd "$PROJECT_DIR"

source .venv/bin/activate
exec python -m uvicorn api_server:app --host 0.0.0.0 --port 8000
