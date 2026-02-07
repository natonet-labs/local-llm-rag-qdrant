# Qdrant Native Helper

This document describes how to build, run, troubleshoot, and manage Qdrant natively without Docker, so your local RAG stack stays fully native.

---

## 1. Prereqs for native Qdrant build (macOS ARM)

You only *need* a working Rust toolchain. Homebrew `protobuf` / `llvm` are optional and not required for your current setup.

### 1.1 Install Rust via rustup

If you haven’t already:

```bash
# Install rustup via Homebrew
brew install rustup

# Initialize Rust toolchain (this is the critical step)
rustup default stable
```

This downloads and installs `cargo`, `rustc`, `rustfmt`, etc.

### 1.2 Ensure `cargo` is on PATH

Rustup puts its binaries in `~/.cargo/bin`. Add that to your shell:

```bash
echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

Sanity check:

```bash
which cargo
cargo --version
rustc --version
# Expect something like:
# /Users/<you>/.cargo/bin/cargo
# cargo 1.93.0 (...)
```

You can ignore `llvm` as a CLI; there is no `llvm` binary to run. macOS’s own `clang` is usually enough.

---

## 2. Build Qdrant from source

Pick a project directory:

```bash
cd ~/projects
git clone https://github.com/qdrant/qdrant.git
cd qdrant
```

(Optional, you already did this):

```bash
rustup component add rustfmt
```

Build Qdrant in release mode:

```bash
cargo build --release --bin qdrant
```

- First build can take a while (downloads crates, compiles everything).
- Subsequent builds are much faster thanks to cached artifacts.

The resulting binary will be here:

```bash
~/projects/qdrant/target/release/qdrant
```

---

## 3. Running Qdrant (foreground and background)

### 3.1 Foreground (debugging)

```bash
cd ~/projects/qdrant
./target/release/qdrant
```

Leave this terminal open; logs print here. Qdrant listens on port `6333` by default.

Health check from another terminal:

```bash
curl http://127.0.0.1:6333/healthz
```

You should see an `OK` or small JSON.

### 3.2 Background (simple `nohup`)

```bash
cd ~/projects/qdrant
nohup ./target/release/qdrant > qdrant.log 2>&1 &
```

- Logs go to `qdrant.log` in the repo.
- Check if it’s running:

```bash
ps aux | grep qdrant | grep target/release
```

Stop it:

```bash
pkill -f "target/release/qdrant"
```

---

## 4. Unified helper script (`qdrant.sh`)

Use a single script to start/stop/restart/status/logs.

Create `qdrant.sh` in your `local-rag-text` project (or wherever you prefer):

```bash
#!/usr/bin/env bash
set -euo pipefail

# Configuration
QDRANT_DIR="${QDRANT_DIR:-$HOME/projects/qdrant}"
QDRANT_BIN="$QDRANT_DIR/target/release/qdrant"
LOG_FILE="${QDRANT_DIR}/qdrant.log"

# Ensure Rust/Cargo bin is on PATH
export PATH="$HOME/.cargo/bin:$PATH"

# Only show warnings and errors from Qdrant (hides INFO HTTP logs)
export QDRANT__LOG_LEVEL=warn

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
  if is_running; then
    pkill -f "$QDRANT_BIN"
    echo "Qdrant stopped."
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
```

Make it executable:

```bash
chmod +x qdrant.sh
```

Usage:

```bash
./qdrant.sh start
./qdrant.sh status
./qdrant.sh logs
./qdrant.sh stop
./qdrant.sh restart
```

---

## 5. Qdrant as a launchd service (auto-start on login)

To align with your `com.localragtext.api` service, create a launch agent for Qdrant so it starts automatically after reboot.

Create `~/Library/LaunchAgents/com.localragtext.qdrant.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>com.localragtext.qdrant</string>

    <key>ProgramArguments</key>
    <array>
      <string>/bin/bash</string>
      <string>/Users/username/projects/local-rag-text/qdrant.sh</string>
      <string>start</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/Users/username/projects/local-rag-text</string>

    <key>EnvironmentVariables</key>
    <dict>
      <key>PATH</key>
      <string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:/Users/username/.cargo/bin</string>
    </dict>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>
  </dict>
</plist>
```

Replace `username` and paths to match your user and project location.

Load and start:

```bash
launchctl load  ~/Library/LaunchAgents/com.localragtext.qdrant.plist
launchctl start com.localragtext.qdrant
```

Check:

```bash
launchctl list | grep com.localragtext.qdrant
lsof -i :6333
```

Restart after plist edits:

```bash
launchctl unload ~/Library/LaunchAgents/com.localragtext.qdrant.plist
launchctl load   ~/Library/LaunchAgents/com.localragtext.qdrant.plist
```

Stop/start by label:

```bash
launchctl stop  com.localragtext.qdrant
launchctl start com.localragtext.qdrant
```

---

## 6. Reset / recreate Qdrant data

To wipe Qdrant’s data and re-ingest from scratch:

1. Stop Qdrant:

   ```bash
   ./qdrant.sh stop
   ```

2. Remove its storage directory (default `storage` inside the repo):

   ```bash
   cd ~/projects/qdrant
   rm -rf storage
   ```

3. Start Qdrant again:

   ```bash
   ./qdrant.sh start
   ```

4. Re-ingest your PDFs (from your RAG project):

   ```bash
   cd ~/projects/local-rag-text
   source .venv/bin/activate
   ./ingest_pdf.sh --force
   ```

---

## 7. Troubleshooting

### 7.1 Is Qdrant listening on 6333?

```bash
lsof -i :6333
```

Should show a `qdrant` process bound to that port.

### 7.2 Health endpoint

```bash
curl http://127.0.0.1:6333/healthz
```

If no response, Qdrant is not running or launchd/`qdrant.sh` failed.

### 7.3 Logs

If started via `qdrant.sh`:

```bash
cd ~/projects/qdrant
tail -n 100 qdrant.log
tail -f qdrant.log
```

Look for storage path or port errors.

---

## 8. Integration with your RAG stack

Your `.env` for the Python RAG code continues to use localhost:

```env
QDRANT_HOST=127.0.0.1
QDRANT_PORT=6333
QDRANT_COLLECTION=docs
```

And in `rag.py` you already have:

```python
from qdrant_client import QdrantClient

client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
```

***