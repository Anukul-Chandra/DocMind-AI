"""PostgreSQL-backed implementation of the ConversationRepository interface."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select

from app.db import models as db
from app.db.session import SessionFactory
from app.repositories.interfaces import ConversationRepository
from app.services.chat_domain import ConversationMessage, ConversationMeta

#: Maximum characters used for the auto-generated conversation title.
TITLE_MAX_LENGTH = 60


class PostgresConversationRepository(ConversationRepository):
    """PostgreSQL conversation repository.

    Persists conversations in the ``conversations`` table and messages in the
    ``chat_messages`` table. Every operation is scoped to an ``owner_id`` so
    a caller can never read or mutate another user's conversations: unknown
    or not-owned conversations read as empty / ``None`` / ``False``.
    """

    def __init__(self, session_factory: SessionFactory) -> None:
        """Initialize the repository with a session factory.

        Args:
            session_factory: A callable returning a fresh session per
                operation.
        """
        self._session_factory = session_factory

    def create_conversation(self, owner_id: str) -> str:
        """Create a new empty conversation owned by a user.

        Args:
            owner_id: The user id that owns the conversation.

        Returns:
            An identifier for the new conversation.
        """
        conversation_id = str(uuid.uuid4())
        with self._session_factory() as session:
            session.add(
                db.Conversation(
                    id=conversation_id,
                    user_id=owner_id,
                    created_at=datetime.now(timezone.utc),
                )
            )
            try:
                session.commit()
            except Exception:
                session.rollback()
                raise
        return conversation_id

    def list_conversations(self, owner_id: str) -> list[ConversationMeta]:
        """Return all conversations owned by a user, newest first.

        Args:
            owner_id: The user id whose conversations to return.

        Returns:
            A list of conversation summaries owned by the user.
        """
        with self._session_factory() as session:
            count_col = func.count(db.ChatMessage.id)
            rows = (
                session.execute(
                    select(db.Conversation, count_col)
                    .outerjoin(
                        db.ChatMessage,
                        db.ChatMessage.conversation_id == db.Conversation.id,
                    )
                    .where(db.Conversation.user_id == owner_id)
                    .group_by(db.Conversation.id)
                    .order_by(db.Conversation.created_at.desc())
                )
                .all()
            )
        return [
            ConversationMeta(
                conversation_id=conversation.id,
                owner_id=conversation.user_id,
                title=conversation.title,
                created_at=conversation.created_at,
                updated_at=conversation.created_at,
                message_count=int(count),
            )
            for conversation, count in rows
        ]

    def get_conversation(
        self, conversation_id: str, owner_id: str
    ) -> ConversationMeta | None:
        """Return a conversation if it belongs to the owner.

        Args:
            conversation_id: The conversation identifier.
            owner_id: The expected owner of the conversation.

        Returns:
            The matching conversation metadata, or None if it is unknown or
            belongs to another owner.
        """
        with self._session_factory() as session:
            row = session.execute(
                select(db.Conversation).where(
                    db.Conversation.id == conversation_id,
                    db.Conversation.user_id == owner_id,
                )
            ).scalar_one_or_none()
        if row is None:
            return None
        with self._session_factory() as session:
            count = session.scalar(
                select(func.count(db.ChatMessage.id)).where(
                    db.ChatMessage.conversation_id == conversation_id
                )
            )
        return ConversationMeta(
            conversation_id=row.id,
            owner_id=row.user_id,
            title=row.title,
            created_at=row.created_at,
            updated_at=row.created_at,
            message_count=int(count or 0),
        )

    def get_messages(
        self, conversation_id: str, owner_id: str
    ) -> list[ConversationMessage]:
        """Return the messages for a conversation if owned by the caller.

        Args:
            conversation_id: The conversation identifier.
            owner_id: The expected owner of the conversation.

        Returns:
            The conversation's messages, or an empty list if the conversation
            is unknown or belongs to another owner.
        """
        with self._session_factory() as session:
            owned = session.execute(
                select(db.Conversation).where(
                    db.Conversation.id == conversation_id,
                    db.Conversation.user_id == owner_id,
                )
            ).scalar_one_or_none()
            if owned is None:
                return []
            rows = (
                session.execute(
                    select(db.ChatMessage)
                    .where(db.ChatMessage.conversation_id == conversation_id)
                    .order_by(db.ChatMessage.id)
                )
                .scalars()
                .all()
            )
        return [
            ConversationMessage(
                role=row.role,
                content=row.content,
                conversation_id=row.conversation_id,
            )
            for row in rows
        ]

    def add_exchange(
        self,
        conversation_id: str,
        owner_id: str,
        user_message: str,
        assistant_response: str,
    ) -> None:
        """Record a user/assistant exchange, deriving the title on first use.

        Ownership is enforced: exchanges for a conversation owned by another
        user are ignored.

        Args:
            conversation_id: The conversation identifier.
            owner_id: The user id that owns the conversation.
            user_message: The user's question.
            assistant_response: The assistant's answer.
        """
        now = datetime.now(timezone.utc)
        with self._session_factory() as session:
            conversation = session.get(db.Conversation, conversation_id)
            if conversation is None or conversation.user_id != owner_id:
                return
            if conversation.title is None:
                conversation.title = _derive_title(user_message)
            session.add(
                db.ChatMessage(
                    conversation_id=conversation_id,
                    user_id=owner_id,
                    role="user",
                    content=user_message,
                    created_at=now,
                )
            )
            session.add(
                db.ChatMessage(
                    conversation_id=conversation_id,
                    user_id=owner_id,
                    role="assistant",
                    content=assistant_response,
                    created_at=now,
                )
            )
            try:
                session.commit()
            except Exception:
                session.rollback()
                raise

    def rename_conversation(
        self, conversation_id: str, owner_id: str, title: str
    ) -> bool:
        """Rename a conversation if it belongs to the owner.

        Args:
            conversation_id: The conversation identifier.
            owner_id: The expected owner of the conversation.
            title: The new conversation title.

        Returns:
            True if the conversation was found, owned by the caller, and
            renamed.
        """
        with self._session_factory() as session:
            row = session.execute(
                select(db.Conversation).where(
                    db.Conversation.id == conversation_id,
                    db.Conversation.user_id == owner_id,
                )
            ).scalar_one_or_none()
            if row is None:
                return False
            row.title = title
            try:
                session.commit()
            except Exception:
                session.rollback()
                raise
            return True

    def delete_conversation(self, conversation_id: str, owner_id: str) -> bool:
        """Delete a conversation and its messages if owned by the caller.

        Args:
            conversation_id: The conversation identifier.
            owner_id: The expected owner of the conversation.

        Returns:
            True if the conversation was found, owned by the caller, and
            deleted.
        """
        with self._session_factory() as session:
            row = session.execute(
                select(db.Conversation).where(
                    db.Conversation.id == conversation_id,
                    db.Conversation.user_id == owner_id,
                )
            ).scalar_one_or_none()
            if row is None:
                return False
            session.execute(
                delete(db.ChatMessage).where(
                    db.ChatMessage.conversation_id == conversation_id
                )
            )
            session.delete(row)
            try:
                session.commit()
            except Exception:
                session.rollback()
                raise
            return True


def _derive_title(user_message: str) -> str:
    """Derive a deterministic title from the first user message.

    Args:
        user_message: The first user message in the conversation.

    Returns:
        A single-line truncated title, falling back to a default when the
        message is empty.
    """
    message = user_message.strip()
    if not message:
        return "New chat"
    message = " ".join(message.split())
    if len(message) > TITLE_MAX_LENGTH:
        message = message[: TITLE_MAX_LENGTH].rstrip() + "…"
    return message
