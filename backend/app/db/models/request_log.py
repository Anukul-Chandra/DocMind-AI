"""Request log entry model."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.utils import utcnow


class RequestLogEntry(Base):
    """A structured log entry for an API request."""

    __tablename__ = "request_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    method: Mapped[str] = mapped_column(String(16), default="")
    path: Mapped[str] = mapped_column(String(1024), default="")
    status_code: Mapped[int] = mapped_column(Integer, default=0)
    user_id: Mapped[str] = mapped_column(String(64), default="")
    workspace_id: Mapped[str] = mapped_column(String(64), default="")
    conversation_id: Mapped[str] = mapped_column(String(64), default="")
    provider: Mapped[str] = mapped_column(String(255), default="")
    model: Mapped[str] = mapped_column(String(255), default="")
    question: Mapped[str] = mapped_column(Text, default="")
    retrieved_chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    response_time_ms: Mapped[float] = mapped_column(Float, default=0.0)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
