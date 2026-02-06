#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# Configuration
# ============================================================================

FORCE=${1:-}  # ./ingest_pdf.sh --force
FORCE_ARG=""
if [[ "$FORCE" == "--force" ]]; then
    FORCE_ARG="--force"
fi

PROJECTDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECTDIR"

# ============================================================================
# Setup
# ============================================================================

source .venv/bin/activate

# ============================================================================
# Process PDFs
# ============================================================================

# Auto-process ALL .pdf files in pdf/ folder
PDF_FILES=(pdf/*.pdf)

if [[ ${#PDF_FILES[@]} -eq 0 ]]; then
    echo "No PDF files found in pdf/ folder."
    exit 1
fi

echo "Found ${#PDF_FILES[@]} PDF files. Processing..."
for PDF_PATH in "${PDF_FILES[@]}"; do
    PDF_NAME=$(basename "$PDF_PATH" .pdf)
    SOURCE_PREFIX="$PDF_NAME"
    
    echo ""
    echo "=== Processing $PDF_PATH (prefix: $SOURCE_PREFIX) ==="
    
    # ingest_pdf.py already handles dedupe via document_exists()
    python ingest_pdf.py $FORCE_ARG --pdf "$PDF_PATH" --source-prefix "$SOURCE_PREFIX"
done

echo ""
echo "✅ Batch ingestion complete!"
echo ""
echo "Next steps:"
echo "  View results:  python rag.py --list-docs"
echo "  Ask a question: python rag.py --ask 'Your question here'"
