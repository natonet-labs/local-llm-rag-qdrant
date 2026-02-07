#!/usr/bin/env bash
set -euo pipefail

# Configuration
QDRANT_DIR="${QDRANT_DIR:-$HOME/projects/qdrant}"
QDRANT_BIN="$QDRANT_DIR/target/release/qdrant"
LOG_FILE="${QDRANT_DIR}/qdrant.log"

# Ensure Rust/Cargo bin is on PATH
export PATH="$HOME/.cargo/bin:$PATH"

# Only show warnings and errors from Qdrant (hides INFO HTTP logs)
export QDRANT__LOG_LEVEL="${QDRANT__LOG_LEVEL:-warn}"

usage() {
  cat <<EOF
Usage: $(basename "$0") {start|stop|restart|status|logs}

Commands:
  start    Start Qdrant in the background
  stop     Stop Qdrant
  restart  Restart Qdrant
  status   Show whether Qdrant is running
  logs     Tail Qdrant log file
EOF
  exit 1
}

ensure_binary() {
  if [[ ! -x "$QDRANT_BIN" ]]; then
    echo "Qdrant binary not found at: $QDRANT_BIN"
    echo "Build it once with:"
    echo "  cd \"$QDRANT_DIR\" && cargo build --release --bin qdrant"
    exit 1
  fi
}

is_running() {
  pgrep -f "$QDRANT_BIN" >/dev/null 2>&1
}

start_qdrant() {
  ensure_binary

  if is_running; then
    echo "Qdrant is already running."
    exit 0
  fi

  echo "Starting Qdrant from $QDRANT_BIN ..."
  cd "$QDRANT_DIR"
  nohup "$QDRANT_BIN" > "$LOG_FILE" 2>&1 &

  sleep 2

  if is_running; then
    echo "Qdrant started. Logs: $LOG_FILE"
  else
    echo "Failed to start Qdrant. Check logs: $LOG_FILE"
    exit 1
  fi
}

stop_qdrant() {
  if pgrep -f "$QDRANT_BIN" >/dev/null 2>&1; then
    pkill -f "$QDRANT_BIN"
    echo "Qdrant stopped (by binary path)."
  elif lsof -i :6333 >/dev/null 2>&1; then
    # Fallback: kill whatever is listening on 6333
    PID=$(lsof -ti :6333 || true)
    if [[ -n "$PID" ]]; then
      kill "$PID"
      echo "Qdrant (or another process) on :6333 was killed (PID $PID)."
    else
      echo "No process found on :6333."
    fi
  else
    echo "Qdrant is not running."
  fi
}

status_qdrant() {
  if is_running; then
    echo "Qdrant is running (PID(s): $(pgrep -f "$QDRANT_BIN" | tr '\n' ' '))."
  else
    echo "Qdrant is not running."
  fi
}

logs_qdrant() {
  if [[ ! -f "$LOG_FILE" ]]; then
    echo "Log file not found: $LOG_FILE"
    exit 1
  fi
  tail -n 100 -f "$LOG_FILE"
}

cmd="${1:-}"
case "$cmd" in
  start)   start_qdrant ;;
  stop)    stop_qdrant ;;
  restart) stop_qdrant; start_qdrant ;;
  status)  status_qdrant ;;
  logs)    logs_qdrant ;;
  *)       usage ;;
esac
