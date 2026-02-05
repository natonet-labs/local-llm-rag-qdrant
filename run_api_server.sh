#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
cd "$PROJECT_DIR"

VENV_DIR=".venv"
PYTHON_BIN="python3.14"

# 1) Create venv if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
  echo "[run_api_server] Creating venv with $PYTHON_BIN..."
  "$PYTHON_BIN" -m venv "$VENV_DIR"
  source "$VENV_DIR/bin/activate"
  echo "[run_api_server] Installing requirements..."
  pip install --upgrade pip
  pip install -r requirements.txt
else
  # 2) Activate existing venv
  source "$VENV_DIR/bin/activate"
fi

# Optional: ensure deps are up to date on every run (uncomment if you like)
# echo "[run_api_server] Ensuring requirements are installed..."
# pip install -r requirements.txt

echo "[run_api_server] Starting uvicorn on 0.0.0.0:8000..."
exec python -m uvicorn api_server:app --host 0.0.0.0 --port 8000
