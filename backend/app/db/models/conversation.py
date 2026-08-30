"""Conversation model."""

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.utils import utcnow


class Conversation(Base):
    """A chat conversation owned by a user.

    Each conversation is scoped to a single ``user_id`` (ownership is enforced
    at the repository layer) and carries an optional, server-persisted
    ``title`` derived from the first user message.
    """

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
