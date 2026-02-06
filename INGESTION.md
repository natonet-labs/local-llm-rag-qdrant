# Ingestion Helper

## PDF Ingestion Options

Your local RAG system supports **4 flexible ingestion patterns** for different use cases. All automatically handle deduplication, UUIDs, and collection creation.

| Command | Scope | Behavior | Speed | Use Case |
|---------|-------|----------|-------|----------|
| `./ingest_pdf.sh` | **All PDFs** | **Skip existing**, ingest new | Fastest (~2min) | **Normal workflow** |
| `./ingest_pdf.sh --force` | **All PDFs** | **Replace all** (delete+re-ingest) | ~2.5min | **Full refresh** |
| `python ingest_pdf.py --pdf pdf/file.pdf --source-prefix MyDoc` | **Single PDF** | **Skip if exists** | ~30s | **Add one doc** |
| `python ingest_pdf.py --force --pdf pdf/file.pdf --source-prefix MyDoc` | **Single PDF** | **Replace** (delete+re-ingest) | ~30s | **Update one doc** |
| `python rag.py --truncate` | **Everything** | **Nuclear wipe** (collection deleted) | 1s | **Fresh start** |

## Quick Start Workflow

```bash
# 1. Fresh setup
python rag.py --truncate    # Type "DELETE"
./ingest_pdf.sh             # Ingest all pdf/*.pdf

# 2. Add/update one PDF
python ingest_pdf.py --force --pdf pdf/New.pdf --source-prefix New

# 3. Full refresh
./ingest_pdf.sh --force

# 4. Check results
python rag.py --list-docs
```

## Detailed Commands

### 1. **Batch Normal** (skip existing)
```bash
./ingest_pdf.sh
```
```
Found 4 PDF files. Processing...
=== Processing pdf/Psychology2e.pdf ===
⚠️  Source 'Psychology2e' already exists. Skipping.
=== Processing pdf/New.pdf ===
Indexing 1500 docs with prefix 'New'...
✅ Batch complete!
```

### 2. **Batch Force** (replace all)
```bash
./ingest_pdf.sh --force
```
```
=== Processing pdf/Psychology2e.pdf ===
🗑️  Deleted 2508 existing chunks for 'Psychology2e'
Indexing 2508 docs...
```

### 3. **Single Normal**
```bash
python ingest_pdf.py --pdf pdf/New.pdf --source-prefix New
```
**Skips** if `New-p*` points exist.

### 4. **Single Force**
```bash
python ingest_pdf.py --force --pdf pdf/New.pdf --source-prefix New
```
**Deletes** all `New-p*` points first, then re-ingests.

### 5. **Full Reset**
```bash
python rag.py --truncate  # Type "DELETE"
```
Deletes entire `docs` collection. Next ingest recreates it.

## Smart Behaviors

- **`document_exists()`**: Skips ingestion if prefix exists (e.g. `Psychology2e-p0-c0`)
- **`delete_by_source_prefix()`**: `--force` deletes **only matching prefix**
- **`ensure_collection()`**: Auto-creates collection with correct dimensions
- **UUIDs**: No ID collisions, even across re-ingests
- **Batch upsert**: 256 points per Qdrant call

## Status Commands

```bash
python rag.py --list-docs          # Psychology2e (2508 chunks)
python rag.py --debug-info         # Point count + sample doc_ids
python rag.py --ask "test query"   # Test RAG search
```

## File Locations

```
pdf/*.pdf                    # Drop PDFs here
ingest_pdf.sh                # Batch runner
ingest_pdf.py                # Single PDF processor
rag.py                       # Core (truncate, search)
```