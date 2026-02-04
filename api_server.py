from fastapi import FastAPI
from pydantic import BaseModel

from rag import search, build_prompt, ollama_chat

app = FastAPI(title="Local RAG Service")


class RAGRequest(BaseModel):
    question: str
    top_k: int | None = 3


class RAGResponse(BaseModel):
    answer: str
    contexts: list[dict]


@app.post("/rag", response_model=RAGResponse)
def rag_endpoint(req: RAGRequest):
    hits = search(req.question, top_k=req.top_k or 3)
    if not hits:
        return RAGResponse(
            answer="No relevant documents found in the vector store.",
            contexts=[],
        )

    prompt = build_prompt(req.question, hits)
    answer = ollama_chat(prompt)
    return RAGResponse(answer=answer, contexts=hits)
