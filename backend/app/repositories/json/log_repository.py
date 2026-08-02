"""JSON-backed implementation of the LogRepository interface."""

from app.repositories.interfaces import LogRepository
from app.services.logging.request_logger import RequestLogEntry, RequestLogger


class JsonLogRepository(LogRepository):
    """JSONL-backed log repository.

    Delegates to the existing :class:`RequestLogger` so callers depend only on
    the :class:`LogRepository` interface.
    """

    def __init__(self, logger: RequestLogger) -> None:
        """Initialize the repository with a JSONL request logger.

        Args:
            logger: The backing request logger.
        """
        self._logger = logger

    def log(self, entry: RequestLogEntry) -> None:
        """Persist a single structured log entry.

        Args:
            entry: The log entry to persist.
        """
        self._logger.log(entry)
