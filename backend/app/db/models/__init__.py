"""SQLAlchemy ORM models for the PostgreSQL persistence backend.

These models back the repository implementations in
``app.repositories.postgres``. A :class:`User` model is included as a
placeholder for future account features but is not yet wired into any
repository or service.
"""

from app.db.models.chat_message import ChatMessage
from app.db.models.conversation import Conversation
from app.db.models.document import Document
from app.db.models.request_log import RequestLogEntry
from app.db.models.user import User
from app.db.models.workspace import Workspace

__all__ = [
    "ChatMessage",
    "Conversation",
    "Document",
    "RequestLogEntry",
    "User",
    "Workspace",
]
