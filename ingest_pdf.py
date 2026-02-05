import os
from typing import List, Dict

from pypdf import PdfReader
from rag import index_documents


def load_pdf_text_pages(pdf_path: str) -> List[str]:
    reader = PdfReader(pdf_path)
    pages_text: List[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        text = text.strip()
        if text:
            pages_text.append(text)
    return pages_text


def chunk_text(text: str, max_chars: int = 1200, overlap: int = 200) -> List[str]:
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


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pdf",
        type=str,
        required=True,
        help="Path to PDF file (e.g., pdf/Psychology2e.pdf)",
    )
    parser.add_argument(
        "--source-prefix",
        type=str,
        default="pdfsource",
        help="Prefix for logical doc ids (e.g., psych2e, socialpsych)",
    )
    args = parser.parse_args()

    pdf_path = args.pdf
    if not os.path.exists(pdf_path):
        raise SystemExit(f"PDF not found at {pdf_path}")

    docs = build_docs_from_pdf(pdf_path, args.source_prefix)
    print(f"Built {len(docs)} chunks from {pdf_path}")
    index_documents(docs)
    print("Indexed into Qdrant.")


if __name__ == "__main__":
    main()
