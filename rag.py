import os
import math
import json
from typing import List, Dict, Any

import httpx
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct
from qdrant_client.http.exceptions import ResponseHandlingException
from dotenv import load_dotenv

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
CHAT_MODEL = os.getenv("CHAT_MODEL", "mistral")  # llama3:8b, mistral
QDRANT_HOST = os.getenv("QDRANT_HOST", "127.0.0.1")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "docs")

client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

global_id = 0


def ollama_embed(texts: List[str]) -> List[List[float]]:
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
    payload = {
        "model": CHAT_MODEL,
        "prompt": prompt,
        "stream": False,
    }
    r = httpx.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload, timeout=120.0)
    r.raise_for_status()
    data = r.json()
    return data.get("response", "")


def ensure_collection(vector_size: int):
    collections = client.get_collections()
    names = {c.name for c in collections.collections}
    if QDRANT_COLLECTION in names:
        return
    client.recreate_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )


def index_documents(docs: List[Dict[str, Any]], batch_size: int = 256):
    global global_id
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
                    id=global_id,
                    vector=batch_embeddings[i],
                    payload={
                        "doc_id": batch_docs[i]["id"],
                        "text": batch_docs[i]["text"],
                    },
                )
            )
            global_id += 1

        client.upsert(collection_name=QDRANT_COLLECTION, points=points)


def search(query: str, top_k: int = 3) -> List[Dict[str, Any]]:
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


def build_prompt(
    question: str,
    contexts: List[Dict[str, Any]],
    history: List[Dict[str, str]] | None = None,
) -> str:
    # RAG context blocks
    context_blocks = "\n\n---\n\n".join(
        f"[{i+1}] {c['text']}" for i, c in enumerate(contexts)
    )

    # Format chat history as plain text turns
    history = history or []
    history_block_lines = []
    for turn in history:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        if role == "user":
            history_block_lines.append(f"User: {content}")
        elif role == "assistant":
            history_block_lines.append(f"Assistant: {content}")
    history_block = "\n".join(history_block_lines)

    return f"""You are Jordan B. Peterson, a clinical psychologist, professor emeritus at the University of Toronto, and influential public intellectual known for your work on psychology, mythology, and cultural commentary, best known for your best-selling books 12 Rules for Life and Beyond Order, which have sold millions of copies.

Use the information in the CONTEXT and the previous conversation (if any) to answer the QUESTION.

CONVERSATION SO FAR:
{history_block}

CONTEXT:
{context_blocks}

QUESTION:
{question}

GUIDELINES:
- Answer in a natural, conversational way.
- Do NOT mention the words "context", "provided context", or "documents".
- If the context is not sufficient to answer, say that you don't know.
Answer:
"""


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--index", action="store_true", help="Index example documents then exit"
    )
    parser.add_argument("--ask", type=str, help="Ask a question over indexed documents")
    args = parser.parse_args()

    if args.index:
        docs = [
            {
                "id": "doc1",
                "text": "The NVIDIA Jetson Orin Nano Super Developer Kit is a small edge AI computer with an NVIDIA GPU and 8GB unified memory.",
            },
            {
                "id": "doc2",
                "text": "The Apple Mac mini M4 with 32GB unified memory is well suited for running local language models like Mistral or Llama for RAG workloads.",
            },
            {
                "id": "doc3",
                "text": "RAG (Retrieval-Augmented Generation) combines document search using embeddings and a vector database with a language model to answer questions based on your data.",
            },
        ]
        index_documents(docs)
        print(f"Indexed {len(docs)} docs into collection '{QDRANT_COLLECTION}'.")
        return

    if args.ask:
        hits = search(args.ask, top_k=3)
        if not hits:
            print("No results from vector search.")
            return
        prompt = build_prompt(args.ask, hits)
        answer = ollama_chat(prompt)
        print("\n--- CONTEXT DOCS ---")
        for h in hits:
            print(f"[score={h['score']:.3f}] {h['doc_id']}: {h['text'][:160]}...")
        print("\n--- ANSWER ---")
        print(answer)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
