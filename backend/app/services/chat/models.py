from pydantic import BaseModel

from app.services.vectorstore.workspace import DEFAULT_WORKSPACE


class ChatRequest(BaseModel):
    """Request payload for a chat completion."""

    question: str
    conversation_id: str | None = None
    workspace_id: str = DEFAULT_WORKSPACE


class SourceReference(BaseModel):
    """Reference to a document chunk used as a source for an answer."""

    filename: str
    chunk_id: int


class ChatResponse(BaseModel):
    """Response returned by the chat service."""

    answer: str
    provider: str
    model: str
    sources: list[SourceReference]
    conversation_id: str