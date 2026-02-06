# Standard library imports
import argparse
import os
from typing import Dict, List

# Third-party imports
from pypdf import PdfReader

# Local imports
from rag import index_documents, document_exists

# ============================================================================
# Configuration
# ============================================================================

QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "docs")


# ============================================================================
# PDF Processing
# ============================================================================


def load_pdf_text_pages(pdf_path: str) -> List[str]:
    """Extract text from each page of a PDF file."""
    reader = PdfReader(pdf_path)
    pages_text: List[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        text = text.strip()
        if text:
            pages_text.append(text)
    return pages_text


def chunk_text(text: str, max_chars: int = 1200, overlap: int = 200) -> List[str]:
    """Split text into overlapping chunks for RAG indexing."""
    chunks: List[str] = []
    n = len(text)
    start = 0
    while start < n:
        end = min(start + max_chars, n)
        chunks.append(text[start:end])
        if end == n:
            break
        start = end - overlap
    return chunks


def build_docs_from_pdf(pdf_path: str, source_prefix: str) -> List[Dict]:
    """Convert PDF to document chunks with metadata."""
    pages = load_pdf_text_pages(pdf_path)
    docs: List[Dict] = []
    for page_idx, page_text in enumerate(pages):
        for i, chunk in enumerate(chunk_text(page_text)):
            docs.append(
                {
                    "id": f"{source_prefix}-p{page_idx}-c{i}",
                    "text": chunk,
                }
            )
    return docs


# ============================================================================
# Main CLI
# ============================================================================


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=str, required=True, help="Path to PDF file")
    parser.add_argument(
        "--source-prefix",
        type=str,
        default="pdfsource",
        help="Prefix for logical doc_ids",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-ingest: delete existing points first",
    )
    args = parser.parse_args()

    pdf_path = args.pdf
    if not os.path.exists(pdf_path):
        raise SystemExit(f"PDF not found at {pdf_path}")

    # Delete old points if --force
    if args.force:
        from rag import delete_by_source_prefix

        count = delete_by_source_prefix(args.source_prefix)
        if count > 0:
            print(f"🗑️  Deleted {count} existing chunks for '{args.source_prefix}'")

    # Skip if exists AND no --force
    elif document_exists(args.source_prefix):
        print(f"⚠️  Source '{args.source_prefix}' already exists. Skipping.")
        print("   Use --force to re-ingest.")
        return

    docs = build_docs_from_pdf(pdf_path, args.source_prefix)
    print(
        f"Indexing {len(docs)} docs with prefix '{args.source_prefix}' into collection '{QDRANT_COLLECTION}'..."
    )
    index_documents(docs)
    print("Indexing completed.")


if __name__ == "__main__":
    main()
