import base64
import logging
import os
import subprocess

from fastapi import APIRouter, Depends, HTTPException, UploadFile, Form, status

from app.api.dependencies import (
    get_chat_service,
    get_conversations_service,
    get_current_user,
    get_query_router,
)
from app.core.config import settings
from app.services.auth import User
from app.services.chat.chat_service import ChatService
from app.services.chat.conversations_service import (
    ConversationNotFoundError,
    ConversationsService,
)
from app.services.chat.query_router import QueryCategory, QueryRouter
from app.services.llm.provider_manager import LLMUnavailableError
from app.services.llm.factory import build_provider_manager

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


@router.get("/diagnostics")
async def diagnostics() -> dict:
    """Runtime diagnostic endpoint - reports configuration state without exposing secrets."""
    # Get git commit SHA
    commit_sha = "unknown"
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            cwd="/app",
        )
        if result.returncode == 0:
            commit_sha = result.stdout.strip()
    except Exception:
        pass

    # Check raw environment variables
    env_vars = {}
    for key in ["OPENROUTER_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY", "AGNES_API_KEY", "OPENCODE_API_KEY"]:
        val = os.environ.get(key)
        env_vars[key] = {
            "configured": bool(val),
            "length": len(val) if val else 0,
        }

    # Check Pydantic settings
    settings_vars = {}
    for key in ["openrouter_api_key", "gemini_api_key", "groq_api_key", "agnes_api_key"]:
        val = getattr(settings, key, "")
        settings_vars[key] = {
            "configured": bool(val),
            "length": len(val) if val else 0,
        }

    # Build provider manager to check initialization
    provider_info = {}
    try:
        pm = build_provider_manager()
        for p in pm._providers:
            provider_name = type(p).__name__
            provider_info[provider_name] = {
                "created": True,
                "model": getattr(p, "model", "unknown"),
            }
            # Check API key on provider (if it has one)
            if hasattr(p, "_api_key"):
                provider_info[provider_name]["api_key_configured"] = bool(p._api_key)
                provider_info[provider_name]["api_key_length"] = len(p._api_key) if p._api_key else 0
            elif hasattr(p, "_model_pool") and hasattr(p._model_pool, "_api_key"):
                # OpenRouter rotating provider
                provider_info[provider_name]["api_key_configured"] = bool(p._api_key)
                provider_info[provider_name]["api_key_length"] = len(p._api_key) if p._api_key else 0
            else:
                provider_info[provider_name]["api_key_configured"] = "n/a (no auth)"
                provider_info[provider_name]["api_key_length"] = 0
        provider_info["total_providers"] = len(pm._providers)
    except Exception as e:
        provider_info["error"] = str(e)

    return {
        "commit_sha": commit_sha,
        "provider_priority": settings.provider_priority,
        "environment_variables": env_vars,
        "pydantic_settings": settings_vars,
        "provider_initialization": provider_info,
    }
