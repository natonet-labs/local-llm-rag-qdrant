from pydantic import BaseModel
from typing import Optional


class RAGRequest(BaseModel):
    question: str
    top_k: Optional[int] = 3


class RAGResponse(BaseModel):
    answer: str
    contexts: list[dict]
