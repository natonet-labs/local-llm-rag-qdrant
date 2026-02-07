# Standard library imports
import argparse
import os
import time
import uuid
from collections import Counter
from typing import Any, Dict, List, Optional

# Third-party imports
import httpx
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.exceptions import ResponseHandlingException
from qdrant_client.http.models import Distance, PointStruct, VectorParams

# Load environment variables
load_dotenv()

# ============================================================================
# Configuration
# ============================================================================

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
CHAT_MODEL = os.getenv("CHAT_MODEL", "mistral")  # fallback to "mistral" if not set
QDRANT_HOST = os.getenv("QDRANT_HOST", "127.0.0.1")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "docs")
MAX_CHAT_HISTORY = 8  # Max messages (4 turns: user/assistant pairs)
MAX_TOP_K = 2  # Max relevant docs to retrieve for context
DEBUG = True

# Initialize Qdrant client
client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)


# ============================================================================
# Ollama Integration (LLM & Embeddings)
# ============================================================================


def ollama_embed(texts: List[str]) -> List[List[float]]:
    """Embed text using Ollama embedding model."""
    # For now, call embeddings one by one using "prompt"
    embeddings: List[List[float]] = []
    for t in texts:
        payload = {"model": EMBED_MODEL, "prompt": t}
        r = httpx.post(f"{OLLAMA_BASE_URL}/api/embeddings", json=payload, timeout=60.0)
        r.raise_for_status()
        data = r.json()
        # Ollama returns {"embedding": [...]} for this endpoint
        emb = data.get("embedding")
        if emb is None:
            raise RuntimeError(f"No embedding in response: {data}")
        embeddings.append(emb)
    return embeddings


def ollama_chat(prompt: str) -> str:
    ctx = 4096
    if CHAT_MODEL.startswith("qwen2.5:7b"):
        ctx = 2048

    start = time.time()
    payload = {
        "model": CHAT_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.5,
            "repeat_penalty": 1.2,
            "top_p": 0.9,
            "top_k": 40,  # (repetition > lower to 20-30; too stiff > raise to 50-60)
            "num_ctx": ctx,
        },
    }

    r = httpx.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload, timeout=120.0)
    r.raise_for_status()
    data = r.json()
    answer = data.get("response", "")

    elapsed = time.time() - start
    if DEBUG:
        print(
            f"[DEBUG] LLM answer length={len(answer.split())} words, time={elapsed:.2f}s"
        )

    return answer


# ============================================================================
# Qdrant Vector Database
# ============================================================================


def ensure_collection(vector_size: int):
    """Create collection if it doesn't exist."""
    collections = client.get_collections()
    names = {c.name for c in collections.collections}
    if QDRANT_COLLECTION in names:
        return
    client.recreate_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )


def document_exists(source_prefix: str) -> bool:
    """Check if any points with this source prefix already exist."""
    try:
        points, _ = client.scroll(
            collection_name=QDRANT_COLLECTION,
            limit=1,
            with_payload=True,
            with_vectors=False,
        )
    except Exception:
        # Collection does not exist or other error → treat as no docs
        return False

    for p in points:
        payload = p.payload or {}
        doc_id = payload.get("doc_id", "")
        if doc_id.startswith(f"{source_prefix}-p"):
            return True

    return False


def index_documents(docs: List[Dict[str, Any]], batch_size: int = 256):
    """Embed documents and upsert into Qdrant collection in batches."""
    texts = [d["text"] for d in docs]
    embeddings = ollama_embed(texts)
    if not embeddings:
        raise RuntimeError("No embeddings returned")

    dim = len(embeddings[0])
    ensure_collection(dim)

    total = len(docs)
    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        batch_docs = docs[start:end]
        batch_embeddings = embeddings[start:end]

        points = []
        for i in range(len(batch_docs)):
            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=batch_embeddings[i],
                    payload={
                        "doc_id": batch_docs[i]["id"],
                        "text": batch_docs[i]["text"],
                    },
                )
            )

        client.upsert(collection_name=QDRANT_COLLECTION, points=points)


def truncate_collection():
    """⚠️  Safely truncate by deleting the collection; it will be recreated on first ingest."""
    collection_name = QDRANT_COLLECTION

    print(f"⚠️  About to DELETE collection '{collection_name}'...")

    # If collection does not exist, just say so and return
    try:
        info = client.get_collection(collection_name)
    except Exception:
        print(f"  Collection '{collection_name}' does not exist. Nothing to delete.")
        return

    print(f"  Currently contains {info.points_count} points")

    confirm = input("Type 'DELETE' to confirm (or Ctrl+C to cancel): ")
    if confirm != "DELETE":
        print("Aborted.")
        return

    client.delete_collection(collection_name)
    print(f"🗑️  Deleted collection '{collection_name}'")
    # No create_collection here; index_documents/ensure_collection will recreate it
    print("✅ Collection will be recreated automatically on next ingest")


def delete_by_source_prefix(source_prefix: str) -> int:
    """Delete all points matching source_prefix-*. Returns count deleted."""
    deleted_count = 0

    while True:
        try:
            # Scroll to find matching points
            points, next_offset = client.scroll(
                collection_name=QDRANT_COLLECTION,
                limit=1000,
                with_payload=True,
                with_vectors=False,
            )
        except Exception as e:
            # Collection does not exist or other error → treat as nothing to delete
            print(
                f"Qdrant scroll error (likely no collection '{QDRANT_COLLECTION}'): {e}"
            )
            return 0

        ids_to_delete = []
        for p in points:
            payload = p.payload or {}
            doc_id = payload.get("doc_id", "")
            if doc_id.startswith(f"{source_prefix}-p"):
                ids_to_delete.append(p.id)

        if ids_to_delete:
            client.delete(
                collection_name=QDRANT_COLLECTION,
                points_selector=models.PointIdsList(points=ids_to_delete),
            )
            deleted_count += len(ids_to_delete)
            print(f"Deleted {len(ids_to_delete)} points for {source_prefix}")
        else:
            if next_offset is None:
                break

        if next_offset is None:
            break

    return deleted_count


# ============================================================================
# Search & Retrieval
# ============================================================================


def search(query: str, top_k: int = MAX_TOP_K) -> List[Dict[str, Any]]:
    """Search for relevant documents using semantic similarity."""
    query_vec = ollama_embed([query])[0]

    try:
        res = client.query_points(
            collection_name=QDRANT_COLLECTION,
            query=query_vec,
            limit=top_k,
            with_payload=True,
        )
    except ResponseHandlingException as e:
        print(f"Error searching Qdrant: {e}")
        return []

    out: List[Dict[str, Any]] = []
    for point in res.points:
        payload = point.payload or {}
        out.append(
            {
                "score": point.score,
                "doc_id": payload.get("doc_id"),
                "text": payload.get("text", ""),
            }
        )
    return out


def list_documents(
    limit: int = 1000,
    offset: Optional[int] = None,
    verbose: bool = False,  # ← New flag
) -> List[str]:
    """Return logical document prefixes with chunk counts as formatted strings.

    Args:
        verbose: If True, print DEBUG scroll info during collection.
    """
    sources = Counter()

    batch = 0
    while True:
        if verbose:
            print(f"DEBUG scroll: batch={batch}, offset={offset}, limit={limit}")

        points, next_offset = client.scroll(
            collection_name=QDRANT_COLLECTION,
            limit=limit,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )

        for p in points:
            payload = p.payload or {}
            doc_id = payload.get("doc_id")
            if not doc_id:
                continue
            prefix = doc_id.split("-p", 1)[0]
            if prefix:
                sources[prefix] += 1

        if next_offset is None:
            break

        offset = next_offset
        batch += 1

    # Format as "name (count chunks)" and sort
    formatted = [f"{name} ({count} chunks)" for name, count in sorted(sources.items())]

    # Print only if verbose (for --debug-info or manual debugging)
    if verbose:
        for line in formatted:
            print(line)

    return formatted


def debug_collection_info() -> None:
    """Print Qdrant collection metadata and a sample of doc_ids."""
    info = client.get_collection(QDRANT_COLLECTION)
    print(f"Collection '{QDRANT_COLLECTION}': {info.points_count} points")

    # Sample a few points to see their doc_id prefixes
    points, _ = client.scroll(
        collection_name=QDRANT_COLLECTION,
        limit=20,
        with_payload=True,
        with_vectors=False,
    )
    print("Sample doc_ids:")
    for p in points:
        payload = p.payload or {}
        print("  ", payload.get("doc_id"))


# ============================================================================
# Prompt Construction & Chat
# ============================================================================


def build_prompt(
    question: str,
    contexts: List[Dict[str, Any]],
    history: List[Dict[str, str]] = None,
) -> str:
    context_blocks = "\n---\n".join(
        [f"{i+1}. {c['text']}" for i, c in enumerate(contexts)]
    )

    history = history or []

    # Deduplicate history
    seen_contents = set()
    deduped_history = []
    for turn in history:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        key = f"{role}:{content}"
        if key not in seen_contents:
            seen_contents.add(key)
            deduped_history.append(turn)

    # Format history
    history_block_lines = []
    for turn in deduped_history:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        if role == "user":
            history_block_lines.append(f"User: {content}")
        elif role == "assistant":
            history_block_lines.append(f"Assistant: {content}")
    history_block = "\n".join(history_block_lines)

    return f"""
SYSTEM: You are a grounded, warm, and professional psychological assistant. Focus on human behavior, meaning, and responsibility.

CONSTRAINTS: 
- Respond ONLY in English (translate non-English input).
- Tone: Calm, precise, one-on-one conversational. 
- Avoid: Lecture-style, motivational-speaker language, group addresses (folks/everyone), and dramatic adjectives (fascinating/important).
- Style: Plain language, no rhetorical flourishes or exclamation marks.

TASK: Answer using the provided context first, then history. If unsupported, say "I may be mistaken." 
FORMAT: 2-4 short paragraphs, 150-220 words. No intro/citations.

HISTORY: {history_block}
CONTEXT: {context_blocks}
QUESTION: {question}

EXAMPLES:
Q: What is groupthink?
A: Groupthink happens when groups prioritize agreement over accuracy.
"""


# ============================================================================
# Main CLI
# ============================================================================


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ask", type=str, help="Ask a question over indexed documents")
    parser.add_argument(
        "--list-docs",
        action="store_true",
        help="List logical document sources stored in Qdrant",
    )
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="Delete all documents from Qdrant (requires confirmation)",
    )
    parser.add_argument(
        "--debug-info",
        action="store_true",
        help="Show Qdrant collection point count and sample doc_ids",
    )
    parser.add_argument("--chat", action="store_true", help="Interactive chat mode")
    args = parser.parse_args()

    if args.chat:
        history = []

        while True:
            try:
                question = input("\nYou: ").strip()
                if question.lower() in ["exit", "quit", "bye"]:
                    break

                hits = search(question, top_k=MAX_TOP_K)
                if not hits:
                    print("No relevant docs found.")
                    continue

                prompt = build_prompt(question, hits, history)
                answer = ollama_chat(prompt)
                print(f"\n🤖 {answer}")

                history.append({"role": "user", "content": question})
                history.append({"role": "assistant", "content": answer})
                if len(history) > MAX_CHAT_HISTORY:
                    history = history[-MAX_CHAT_HISTORY:]

            except KeyboardInterrupt:
                break
        return

    if args.ask:
        hits = search(args.ask, top_k=MAX_TOP_K)
        if not hits:
            print("No relevant docs found.")
            return
        prompt = build_prompt(args.ask, hits)
        answer = ollama_chat(prompt)
        if DEBUG:
            print("\n--- CONTEXT DOCS ---")
            for h in hits:
                print(f"[score={h['score']:.3f}] {h['doc_id']}: {h['text'][:160]}...")
            print("\n--- ANSWER ---")
        print(answer)
        return

    if args.list_docs:
        files = list_documents(verbose=False)
        for name in files:
            print(name)
        return

    if args.truncate:
        truncate_collection()
        return

    if args.debug_info:
        debug_collection_info()
        return

    parser.print_help()


if __name__ == "__main__":
    main()
