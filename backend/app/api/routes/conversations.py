"""REST endpoints for per-user chat conversation history."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_conversations_service, get_current_user
from app.models.responses import DeleteResult, SuccessResponse
from app.services.auth import User
from app.services.chat_domain import ConversationMessage, ConversationMeta
from app.services.chat.conversations_service import (
    ConversationNotFoundError,
    ConversationsService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])


class RenameConversationRequest(BaseModel):
    """Request body for renaming a conversation.

    Attributes:
        title: The new conversation title.
    """

    title: str = Field(..., min_length=1, max_length=200)


@router.get("", response_model=SuccessResponse[list[ConversationMeta]])
def list_conversations(
    current_user: User = Depends(get_current_user),
    conversations_service: ConversationsService = Depends(get_conversations_service),
) -> SuccessResponse[list[ConversationMeta]]:
    """Return the conversations owned by the authenticated user, newest first.

    Args:
        current_user: The authenticated user.
        conversations_service: The ownership-scoped conversation service.

    Returns:
        A success envelope with the user's conversation summaries.
    """
    return SuccessResponse(
        data=conversations_service.list_for_user(current_user.user_id)
    )


@router.post(
    "",
    response_model=SuccessResponse[ConversationMeta],
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    current_user: User = Depends(get_current_user),
    conversations_service: ConversationsService = Depends(get_conversations_service),
) -> SuccessResponse[ConversationMeta]:
    """Create a new empty conversation owned by the authenticated user.

    Args:
        current_user: The authenticated user.
        conversations_service: The ownership-scoped conversation service.

    Returns:
        A success envelope with the created conversation metadata.
    """
    return SuccessResponse(
        data=conversations_service.create(current_user.user_id)
    )


@router.get("/{conversation_id}", response_model=SuccessResponse[ConversationMeta])
def get_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    conversations_service: ConversationsService = Depends(get_conversations_service),
) -> SuccessResponse[ConversationMeta]:
    """Return a conversation owned by the authenticated user.

    Args:
        conversation_id: The conversation identifier.
        current_user: The authenticated user.
        conversations_service: The ownership-scoped conversation service.

    Returns:
        A success envelope with the conversation metadata.

    Raises:
        HTTPException: If the conversation is unknown or belongs to another
            user. The response does not reveal which case occurred.
    """
    try:
        meta = conversations_service.get(conversation_id, current_user.user_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        ) from exc
    return SuccessResponse(data=meta)


@router.get(
    "/{conversation_id}/messages",
    response_model=SuccessResponse[list[ConversationMessage]],
)
def get_messages(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    conversations_service: ConversationsService = Depends(get_conversations_service),
) -> SuccessResponse[list[ConversationMessage]]:
    """Return the messages for a conversation owned by the authenticated user.

    Args:
        conversation_id: The conversation identifier.
        current_user: The authenticated user.
        conversations_service: The ownership-scoped conversation service.

    Returns:
        A success envelope with the conversation's messages.

    Raises:
        HTTPException: If the conversation is unknown or belongs to another
            user. The response does not reveal which case occurred.
    """
    try:
        messages = conversations_service.get_messages(
            conversation_id, current_user.user_id
        )
    except ConversationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        ) from exc
    return SuccessResponse(data=messages)


@router.patch(
    "/{conversation_id}",
    response_model=SuccessResponse[ConversationMeta],
)
def rename_conversation(
    conversation_id: str,
    body: RenameConversationRequest,
    current_user: User = Depends(get_current_user),
    conversations_service: ConversationsService = Depends(get_conversations_service),
) -> SuccessResponse[ConversationMeta]:
    """Rename a conversation owned by the authenticated user.

    Args:
        conversation_id: The conversation identifier.
        body: The rename request containing the new title.
        current_user: The authenticated user.
        conversations_service: The ownership-scoped conversation service.

    Returns:
        A success envelope with the updated conversation metadata.

    Raises:
        HTTPException: If the conversation is unknown or belongs to another
            user. The response does not reveal which case occurred.
    """
    try:
        meta = conversations_service.rename(
            conversation_id, current_user.user_id, body.title
        )
    except ConversationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        ) from exc
    return SuccessResponse(data=meta)


@router.delete(
    "/{conversation_id}",
    response_model=SuccessResponse[DeleteResult],
)
def delete_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    conversations_service: ConversationsService = Depends(get_conversations_service),
) -> SuccessResponse[DeleteResult]:
    """Delete a conversation owned by the authenticated user.

    Args:
        conversation_id: The conversation identifier.
        current_user: The authenticated user.
        conversations_service: The ownership-scoped conversation service.

    Returns:
        A success envelope describing the deletion outcome.

    Raises:
        HTTPException: If the conversation is unknown or belongs to another
            user. The response does not reveal which case occurred.
    """
    try:
        conversations_service.delete(conversation_id, current_user.user_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        ) from exc
    return SuccessResponse(
        data=DeleteResult(conversation_id=conversation_id, status="deleted")
    )
