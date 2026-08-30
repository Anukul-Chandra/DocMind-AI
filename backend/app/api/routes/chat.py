import base64
import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, Form, status

from app.api.dependencies import (
    get_chat_service,
    get_conversations_service,
    get_current_user,
    get_query_router,
)
from app.services.auth import User
from app.services.chat.chat_service import ChatService
from app.services.chat.conversations_service import (
    ConversationNotFoundError,
    ConversationsService,
)
from app.services.chat.query_router import QueryCategory, QueryRouter
from app.services.llm.provider_manager import LLMUnavailableError

logger = logging.getLogger(__name__)


class ChatResponse:
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


ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB per image


router = APIRouter(prefix="/chat", tags=["chat"])


@router.post(
    "/",
    status_code=status.HTTP_200_OK,
)
async def chat(
    question: str = Form(...),
    attachments: list[UploadFile] = Form(default=[]),
    conversation_id: str | None = Form(default=None),
    current_user: User = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
    conversation_svc: ConversationsService = Depends(get_conversations_service),
) -> dict:
    """Answer a question through the ChatService orchestration layer.

    Accepts a text question and optional image attachments (PNG, JPEG, WEBP).
    Images are base64-encoded and forwarded to the LLM provider as multimodal
    content when the provider supports vision. When ``conversation_id`` is
    provided, the exchange is recorded to the owning user's conversation
    history (404 if the conversation belongs to another user).

    Args:
        question: The user's question text.
        attachments: Optional image attachments pasted by the user.
        conversation_id: The conversation to record the exchange in, or None.
        current_user: The authenticated user whose chunks may be retrieved.
        chat_service: The ChatService that orchestrates retrieval and generation.

    Returns:
        A chat response dict with the provider, model, and answer.

    Raises:
        HTTPException: If no LLM provider is available to answer the question,
            or if the conversation is unknown / not owned.
    """
    # Validate and encode attachments
    encoded_images: list[dict] = []
    for upload in attachments:
        if upload.content_type and upload.content_type not in ALLOWED_IMAGE_TYPES:
            logger.warning("Skipping unsupported attachment type: %s", upload.content_type)
            continue
        data = await upload.read()
        if len(data) > MAX_IMAGE_BYTES:
            logger.warning("Skipping attachment exceeding size limit: %s", upload.filename)
            continue
        mime = upload.content_type or "image/png"
        b64 = base64.b64encode(data).decode("ascii")
        encoded_images.append({
            "mime": mime,
            "data": b64,
        })

    # Validate ownership of the target conversation, if provided. This
    # guarantees a user can never write into another user's conversation.
    if conversation_id:
        try:
            conversation_svc.get(conversation_id, current_user.user_id)
        except ConversationNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found.",
            ) from exc

    try:
        response = await chat_service.chat(
            question,
            owner_id=current_user.user_id,
            images=encoded_images if encoded_images else None,
            conversation_id=conversation_id,
        )
    except LLMUnavailableError as exc:
        logger.error("All LLM providers failed for chat request", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The AI service is temporarily unavailable. Please try again later.",
        ) from exc
    return {
        "provider": response.provider,
        "model": response.model,
        "answer": response.text,
        "category": response.category,
        "sources": response.sources,
        "conversation_id": conversation_id,
    }


@router.post(
    "/classify",
    status_code=status.HTTP_200_OK,
)
async def classify(
    question: str = Form(...),
    current_user: User = Depends(get_current_user),
    query_router: QueryRouter = Depends(get_query_router),
) -> dict:
    """Classify a question into a routing category without generating an answer.

    This allows the frontend to show an appropriate loading state before the
    full chat request is made.

    Args:
        question: The user's question text.
        current_user: The authenticated user whose corpus determines relevance.
        query_router: The shared QueryRouter instance.

    Returns:
        A dict with the routing category ("general" | "document" | "metadata").
    """
    category = query_router.classify(question, owner_id=current_user.user_id)
    return {"category": category.value}
