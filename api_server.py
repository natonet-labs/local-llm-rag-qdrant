# Standard library imports
import os

# Third-party imports
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

# Local imports
from rag import build_prompt, ollama_chat, search

# ============================================================================
# Configuration
# ============================================================================

MAX_TURNS = 6

app = FastAPI()

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "session-secret-key"),
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ============================================================================
# Session Management
# ============================================================================


def get_history(request: Request) -> list[dict[str, str]]:
    """Retrieve chat history from session."""
    return request.session.get("history", [])


def save_history(request: Request, history: list[dict[str, str]]) -> None:
    """Save chat history to session, keeping only the last N turns."""
    # keep only the last N turns to avoid overfilling context
    request.session["history"] = history[-MAX_TURNS:]


# ============================================================================
# Chat Endpoints
# ============================================================================


@app.get("/chat", response_class=HTMLResponse)
async def chat_get(request: Request):
    """Display chat interface."""
    # reset history when the page is first loaded, if you want a fresh convo
    request.session["history"] = []
    return templates.TemplateResponse(
        "chat.html",
        {
            "request": request,
            "question": None,
            "answer": None,
        },
    )


@app.post("/chat", response_class=HTMLResponse)
async def chat_post(request: Request, question: str = Form(...)):
    """Process chat message and return answer."""
    # load existing chat history for this browser session
    history = get_history(request)

    # standard RAG pipeline
    results = search(question)
    prompt = build_prompt(question, results, history=history)
    answer = ollama_chat(prompt)

    # append this turn to history
    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": answer})
    save_history(request, history)

    return templates.TemplateResponse(
        "chat.html",
        {
            "request": request,
            "question": question,
            "answer": answer,
        },
    )
