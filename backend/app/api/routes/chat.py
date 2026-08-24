import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.dependencies import get_chat_service, get_current_user
from app.services.auth import User
from app.services.chat.chat_service import ChatService
from app.services.llm.provider_manager import LLMUnavailableError

logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    """Request payload for a chat completion."""

    question: str


class ChatResponse(BaseModel):
    """Response returned by the chat endpoint.

    Attributes:
        provider: The LLM provider that produced the answer.
        model: The model used to produce the answer.
        answer: The generated answer text.
        category: Routing decision that produced the answer
            ("general" | "document" | "metadata").
        sources: Document chunks that contributed to the answer. Empty
            unless retrieval was actually used.
    """

    provider: str
    model: str
    answer: str
    category: str = "general"
    sources: list[dict] = []


router = APIRouter(prefix="/chat", tags=["chat"])


@router.post(
    "/",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
)
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    """Answer a question through the ChatService orchestration layer.

    The endpoint only delegates to ChatService; it performs no retrieval, no
    prompt construction, and no direct provider calls. Authentication is
    required and the authenticated user's id is passed as the owner scope so
    retrieval can only use chunks owned by that user.

    Args:
        request: The chat request containing the user's question.
        current_user: The authenticated user whose chunks may be retrieved.
        chat_service: The ChatService that orchestrates retrieval and generation.

    Returns:
        A chat response with the provider, model, and answer.

    Raises:
        HTTPException: If no LLM provider is available to answer the question.
    """
    try:
        response = await chat_service.chat(
            request.question,
            owner_id=current_user.user_id,
        )
    except LLMUnavailableError as exc:
        logger.error("All LLM providers failed for chat request", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The AI service is temporarily unavailable. Please try again later.",
        ) from exc
    return ChatResponse(
        provider=response.provider,
        model=response.model,
        answer=response.text,
        category=response.category,
        sources=response.sources,
    )
