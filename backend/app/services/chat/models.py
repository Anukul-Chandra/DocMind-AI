from enum import Enum

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


class StreamEventType(str, Enum):
    """Discriminator for the events sent over the chat stream."""

    SOURCES = "sources"
    DELTA = "delta"
    PROVENANCE = "provenance"
    ERROR = "error"


class ChatStreamEvent(BaseModel):
    """One event emitted over the streaming chat endpoint.

    Attributes:
        type: The kind of event (sources, delta, provenance, or error).
        data: The event payload as a JSON-compatible mapping.
    """

    type: StreamEventType
    data: dict