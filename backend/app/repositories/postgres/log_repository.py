"""PostgreSQL-backed implementation of the LogRepository interface."""

from datetime import datetime, timezone

from app.db import models as db
from app.db.session import SessionFactory
from app.repositories.interfaces import LogRepository
from app.services.logging.request_logger import RequestLogEntry


class PostgresLogRepository(LogRepository):
    """PostgreSQL log repository.

    Persists structured request logs into the ``request_logs`` table. Logging
    is best-effort (mirroring the JSONL implementation): a database failure
    never propagates to the caller.
    """

    def __init__(self, session_factory: SessionFactory) -> None:
        """Initialize the repository with a session factory.

        Args:
            session_factory: A callable returning a fresh session per
                operation.
        """
        self._session_factory = session_factory

    def log(self, entry: RequestLogEntry) -> None:
        """Persist a single structured log entry.

        Args:
            entry: The log entry to persist.
        """
        try:
            timestamp = datetime.fromisoformat(entry.timestamp)
        except (ValueError, TypeError):
            timestamp = datetime.now(timezone.utc)
        try:
            with self._session_factory() as session:
                session.add(
                    db.RequestLogEntry(
                        request_id=entry.request_id,
                        timestamp=timestamp,
                        workspace_id=entry.workspace_id,
                        conversation_id=entry.conversation_id,
                        provider=entry.provider,
                        model=entry.model,
                        question=entry.question,
                        retrieved_chunk_count=entry.retrieved_chunk_count,
                        response_time_ms=entry.response_time_ms,
                        success=entry.success,
                        error_message=entry.error_message,
                    )
                )
        except Exception:
            # Logging is best-effort; never fail the request.
            return
