"""
API server for RAG chat application using FastAPI.
How to pull models: from models import RAGRequest, RAGResponse
"""

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from rag import search, build_prompt, ollama_chat

app = FastAPI()

# static files (CSS)
app.mount("/static", StaticFiles(directory="static"), name="static")

# templates (HTML)
templates = Jinja2Templates(directory="templates")


@app.get("/chat", response_class=HTMLResponse)
async def chat_get(request: Request):
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
    # simple RAG pipeline
    results = search(question)
    prompt = build_prompt(question, results)
    answer = ollama_chat(prompt)

    return templates.TemplateResponse(
        "chat.html",
        {
            "request": request,
            "question": question,
            "answer": answer,
        },
    )
