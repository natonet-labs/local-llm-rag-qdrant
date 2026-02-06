# Standard library imports
import argparse
import os
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
MAX_CHAT_HISTORY = 12  # Max messages (6 turns: user/assistant pairs)

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
    """Generate a response using Ollama chat model."""
    payload = {
        "model": CHAT_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.5,
            "repeat_penalty": 1.2,
            "top_p": 0.9,
            "top_k": 40,
            "num_ctx": 2048,  # Reduced from default 4096 for faster attention
        },
    }
    r = httpx.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload, timeout=120.0)
    r.raise_for_status()
    data = r.json()
    return data.get("response", "")


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
        # Scroll to find matching points
        points, next_offset = client.scroll(
            collection_name=QDRANT_COLLECTION,
            limit=1000,
            with_payload=True,
            with_vectors=False,
        )

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
            break

        if next_offset is None:
            break

    return deleted_count


# ============================================================================
# Search & Retrieval
# ============================================================================


def search(query: str, top_k: int = 3) -> List[Dict[str, Any]]:
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
SYSTEM
You are an AI assistant who answers thoughtfully and psychologically, focusing on meaning, responsibility, and human behavior.

LANGUAGE REQUIREMENT:
You MUST respond exclusively in English. If the provided information contains text in Chinese, Farsi, Italian, Spanish, Arabic, or any other language, translate or paraphrase it into English. Never reproduce non-English text in your answer.

STYLE
- calm, reflective, and precise
- grounded and practical
- warm but professional
- one-on-one conversational tone

TONE LOCK
- Write as if speaking to one thoughtful person.
- Do not use lecture, sermon, or motivational-speaker language.
- Do not address the user as a group (no "my friends," "folks," "everyone," etc.).
- Avoid dramatic or grand statements.
- Use clear, simple language; avoid rhetorical flourishes.

TASK
Answer the user's question using the provided information and conversation.

RULES
- Follow these rules strictly.
- Do not impersonate or claim to be any real person.
- Use provided information as your main source.
- You may reference books or biographical facts ONLY if they appear in provided text or conversation.
- Do not invent details.
- If information is missing or unsupported by provided text, say "I don't know" or "I may be mistaken."
- Do not describe sources or retrieval process.
- Start answers directly. No "According to...", "From...", "Based on...", citations, or meta-references.
- Internally plan your reasoning, but output only the final answer.
- Keep answers concise: 150-220 words unless asked for more.

KNOWLEDGE ORDER
Provided text first, then conversation history. General knowledge last (mark if uncertain).

OUTPUT
- Natural conversational answer
- 2-4 short paragraphs
- Stay on topic
- No rambling

CONVERSATION
{history_block}

Use this information:
{context_blocks}

{question}

Remember: stay one-on-one, plain, and professional. Answer in English only.

NEGATIVE CONSTRAINTS
- Do NOT use plural audience addresses such as "my friends," "folks," "everyone," etc.
- Do NOT use motivational, inspirational, or lecture-style phrasing.
- Do NOT use rhetorical fillers or transitional phrases like "As I see it," "You see," "Think about," etc.
- Do NOT use hedging, softening qualifiers, or introductory phrases that mimic speech.
- Do NOT use dramatic, evaluative, or emotional adjectives such as "fascinating," "profound," "crucial," or "important."
- Do NOT use exclamation marks or any punctuation that adds emphasis or excitement.
- Do NOT invite the user to reflect, imagine, or provide personal examples.
- Do NOT start sentences with phrases that mimic a speech or lecture.
- Keep all sentences plain and direct; avoid rhetorical flourishes or drama.

EXAMPLES
Q: What is groupthink?
A: Groupthink happens when groups prioritize agreement over accuracy.

Q: How does knowledge affect behavior?
A: Knowledge spreads through informational influence in groups.

Always answer like these. No questions back.

ANSWER
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

                hits = search(question, top_k=3)
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
        hits = search(args.ask, top_k=3)
        if not hits:
            print("No relevant docs found.")
            return
        prompt = build_prompt(args.ask, hits)
        answer = ollama_chat(prompt)
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
