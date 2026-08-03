from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.dependencies import get_rag_chat_service
from app.services.chat.chat_service import ChatService
from app.services.llm.provider_manager import LLMUnavailableError


class ChatRequest(BaseModel):
    """Request payload for a chat completion."""

    question: str


class ChatResponse(BaseModel):
    """Response returned by the chat endpoint.

    Attributes:
        provider: The LLM provider that produced the answer.
        model: The model used to produce the answer.
        answer: The generated answer text.
    """

    provider: str
    model: str
    answer: str


router = APIRouter(prefix="/chat", tags=["chat"])


@router.post(
    "/",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
)
async def chat(
    request: ChatRequest,
    chat_service: ChatService = Depends(get_rag_chat_service),
) -> ChatResponse:
    """Answer a question through the ChatService orchestration layer.

    The endpoint only delegates to ChatService; it performs no retrieval, no
    prompt construction, and no direct provider calls.

    Args:
        request: The chat request containing the user's question.
        chat_service: The ChatService that orchestrates retrieval and generation.

    Returns:
        A chat response with the provider, model, and answer.

    Raises:
        HTTPException: If no LLM provider is available to answer the question.
    """
    try:
        response = await chat_service.chat(request.question)
    except LLMUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"All LLM providers failed: {exc}",
        ) from exc
    return ChatResponse(
        provider=response.provider,
        model=response.model,
        answer=response.text,
    )
