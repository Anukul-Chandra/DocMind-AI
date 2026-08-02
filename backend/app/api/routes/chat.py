import json
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_chat_service
from app.services.chat import (
    ChatRequest,
    ChatResponse,
    ChatService,
    ChatStreamEvent,
)
from app.services.llm.provider_manager import LLMUnavailableError

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/", response_model=ChatResponse, status_code=status.HTTP_200_OK)
async def chat(
    request: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    """Answer a question using the retrieved document context.

    Args:
        request: The chat request containing the user's question.
        chat_service: The ChatService that orchestrates retrieval and generation.

    Returns:
        A ChatResponse with the answer and provider provenance.

    Raises:
        HTTPException: If no LLM provider is available to answer the question.
    """
    try:
        return await chat_service.chat(request)
    except LLMUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"All LLM providers failed: {exc}",
        ) from exc


def _sse(event: ChatStreamEvent) -> str:
    """Serialize a chat stream event to a Server-Sent Events frame.

    Args:
        event: The event to serialize.

    Returns:
        A single SSE ``event:`` / ``data:`` frame as text.
    """
    data = json.dumps(event.data)
    return f"event: {event.type.value}\ndata: {data}\n\n"


@router.post("/stream", status_code=status.HTTP_200_OK)
async def chat_stream(
    request: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service),
) -> StreamingResponse:
    """Stream an answer to a question using the retrieved document context.

    Behaves like ``POST /chat/`` but returns the response as a Server-Sent
    Events stream. Retrieval, conversation memory, source attribution, and
    request logging are preserved. Providers without native streaming fall
    back to chunked (SSE) output transparently.

    Args:
        request: The chat request containing the user's question.
        chat_service: The ChatService orchestrating retrieval and stream.

    Returns:
        A StreamingResponse over ``text/event-stream``.
    """
    async def event_stream() -> AsyncIterator[str]:
        async for event in chat_service.stream_chat(request):
            yield _sse(event)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )