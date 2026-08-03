"""PostgreSQL-backed implementation of the ConversationRepository interface."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.db import models as db
from app.db.session import SessionFactory
from app.repositories.interfaces import ConversationRepository


class PostgresConversationRepository(ConversationRepository):
    """PostgreSQL conversation repository.

    Persists conversations in the ``conversations`` table and messages in the
    ``chat_messages`` table, mirroring the in-memory
    :class:`ConversationMemory` semantics (unknown conversations yield an
    empty history, and ``add_exchange`` implicitly creates the conversation).
    """

    def __init__(self, session_factory: SessionFactory) -> None:
        """Initialize the repository with a session factory.

        Args:
            session_factory: A callable returning a fresh session per
                operation.
        """
        self._session_factory = session_factory

    def create_conversation(self) -> str:
        """Create a new empty conversation.

        Returns:
            An identifier for the new conversation.
        """
        conversation_id = str(uuid.uuid4())
        with self._session_factory() as session:
            session.add(
                db.Conversation(
                    id=conversation_id,
                    created_at=datetime.now(timezone.utc),
                )
            )
        return conversation_id

    def get_history(self, conversation_id: str) -> list[dict[str, str]]:
        """Return the stored message history for a conversation.

        Args:
            conversation_id: The conversation identifier.

        Returns:
            The message history, or an empty list if unknown.
        """
        with self._session_factory() as session:
            rows = (
                session.execute(
                    select(db.ChatMessage)
                    .where(db.ChatMessage.conversation_id == conversation_id)
                    .order_by(db.ChatMessage.id)
                )
                .scalars()
                .all()
            )
        return [{"role": row.role, "content": row.content} for row in rows]

    def add_exchange(
        self,
        conversation_id: str,
        user_message: str,
        assistant_response: str,
    ) -> None:
        """Record a user/assistant exchange.

        Args:
            conversation_id: The conversation identifier.
            user_message: The user's question.
            assistant_response: The assistant's answer.
        """
        now = datetime.now(timezone.utc)
        with self._session_factory() as session:
            if session.get(db.Conversation, conversation_id) is None:
                session.add(
                    db.Conversation(id=conversation_id, created_at=now)
                )
            session.add(
                db.ChatMessage(
                    conversation_id=conversation_id,
                    role="user",
                    content=user_message,
                    created_at=now,
                )
            )
            session.add(
                db.ChatMessage(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=assistant_response,
                    created_at=now,
                )
            )
