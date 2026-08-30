"""Domain models for conversation history.

These are the entities exchanged between the conversation repository
implementations and the conversation/chat services. Ownership is carried on
every model so repository and service code can enforce per-user scoping without
reaching into the persistence layer.
"""

from datetime import datetime

from pydantic import BaseModel


class ConversationMessage(BaseModel):
    """A single user or assistant message within a conversation.

    Attributes:
        role: Either ``user`` or ``assistant``.
        content: The message text body.
        conversation_id: The conversation this message belongs to.
    """

    role: str
    content: str
    conversation_id: str = ""


class ConversationMeta(BaseModel):
    """Summary of a conversation for listing and header display.

    Attributes:
        conversation_id: Unique identifier for the conversation.
        owner_id: The user id that owns the conversation.
        title: The server-persisted conversation title, or None until the
            first user message is recorded.
        created_at: When the conversation was created.
        updated_at: When the conversation was last written to.
        message_count: Number of stored messages.
    """

    conversation_id: str
    owner_id: str = ""
    title: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    message_count: int = 0
