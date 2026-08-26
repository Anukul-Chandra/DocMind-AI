import base64
import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, Form, status

from app.api.dependencies import get_chat_service, get_current_user
from app.services.auth import User
from app.services.chat.chat_service import ChatService
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
    current_user: User = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
) -> dict:
    """Answer a question through the ChatService orchestration layer.

    Accepts a text question and optional image attachments (PNG, JPEG, WEBP).
    Images are base64-encoded and forwarded to the LLM provider as multimodal
    content when the provider supports vision.

    Args:
        question: The user's question text.
        attachments: Optional image attachments pasted by the user.
        current_user: The authenticated user whose chunks may be retrieved.
        chat_service: The ChatService that orchestrates retrieval and generation.

    Returns:
        A chat response dict with the provider, model, and answer.

    Raises:
        HTTPException: If no LLM provider is available to answer the question.
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

    try:
        response = await chat_service.chat(
            question,
            owner_id=current_user.user_id,
            images=encoded_images if encoded_images else None,
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
    }
