import os
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from rag import build_prompt, search

MAX_CHAT_HISTORY = 12

app = FastAPI()
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "session-secret-key"),
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
CHAT_MODEL = os.getenv("CHAT_MODEL", "qwen2.5:14b-instruct-q5_K_M")


def get_history(request: Request) -> list[dict[str, str]]:
    """Retrieve chat history from session."""
    return request.session.get("history", [])


def save_history(request: Request, history: list[dict[str, str]]) -> None:
    """Save chat history to session, keeping only the last N turns."""
    request.session["history"] = history[-MAX_CHAT_HISTORY:]


async def ollama_chat_stream(prompt: str) -> AsyncGenerator[str, None]:
    """Stream tokens from Ollama chat model."""
    payload = {
        "model": CHAT_MODEL,
        "prompt": prompt,
        "stream": True,  # Enable streaming
        "options": {
            "temperature": 0.5,
            "repeat_penalty": 1.2,
            "top_p": 0.9,
            "top_k": 40,
            "num_ctx": 4096,
        },
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST", f"{OLLAMA_BASE_URL}/api/generate", json=payload
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.strip():
                    import json

                    try:
                        chunk = json.loads(line)
                        if "response" in chunk:
                            yield chunk["response"]
                    except json.JSONDecodeError:
                        continue


@app.get("/chat", response_class=HTMLResponse)
async def chat_get(request: Request):
    """Display chat interface."""
    request.session["history"] = []  # Reset on page load
    return templates.TemplateResponse(
        "chat.html",
        {"request": request, "question": None, "answer": None},
    )


@app.post("/chat/stream")
async def chat_stream(request: Request, question: str = Form(...)):
    """Stream chat response token-by-token."""
    history = get_history(request)

    # Trim history
    if len(history) > MAX_CHAT_HISTORY:
        history = history[-MAX_CHAT_HISTORY:]

    # RAG retrieval
    results = search(question)
    prompt = build_prompt(question, results, history)

    # Accumulate full answer for history
    full_answer = []

    async def token_generator():
        async for token in ollama_chat_stream(prompt):
            full_answer.append(token)
            yield token

        # Save history after streaming completes
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": "".join(full_answer)})
        save_history(request, history)

    return StreamingResponse(token_generator(), media_type="text/plain")


@app.post("/chat", response_class=HTMLResponse)
async def chat_post(request: Request, question: str = Form(...)):
    """Non-streaming endpoint (keep for compatibility)."""
    history = get_history(request)

    if len(history) > MAX_CHAT_HISTORY:
        history = history[-MAX_CHAT_HISTORY:]

    results = search(question)
    prompt = build_prompt(question, results, history)

    # Collect full response from stream
    answer_parts = []
    async for token in ollama_chat_stream(prompt):
        answer_parts.append(token)

    answer = "".join(answer_parts)

    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": answer})
    save_history(request, history)

    return templates.TemplateResponse(
        "chat.html",
        {"request": request, "question": question, "answer": answer},
    )
