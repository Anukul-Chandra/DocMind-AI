from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_chat_service
from app.services.chat import ChatRequest, ChatResponse, ChatService
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
        return await chat_service.chat(request.question)
    except LLMUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"All LLM providers failed: {exc}",
        ) from exc