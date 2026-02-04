#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# Ask for PDF filename (relative to pdf/)
read -rp "Enter PDF filename under pdf/ (e.g., Psychology2e.pdf): " PDF_NAME

PDF_PATH="pdf/$PDF_NAME"

if [[ ! -f "$PDF_PATH" ]]; then
  echo "File not found: $PDF_PATH"
  exit 1
fi

# Derive a simple source prefix from filename (strip extension)
SOURCE_PREFIX="${PDF_NAME%.*}"

# Activate venv
source .venv/bin/activate

echo "Ingesting $PDF_PATH with source prefix '$SOURCE_PREFIX'..."
python ingest_pdf.py --pdf "$PDF_PATH" --source-prefix "$SOURCE_PREFIX"
