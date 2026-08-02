from pydantic import BaseModel


class ChatRequest(BaseModel):
    """Request payload for a chat completion."""

    question: str


class ChatResponse(BaseModel):
    """Response returned by the chat service."""

    answer: str
    provider: str
    model: str