from pydantic import BaseModel


class ChatRequest(BaseModel):
    """Request payload for a chat completion."""

    question: str


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