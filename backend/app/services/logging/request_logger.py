"""Lightweight request logging for the chat pipeline."""

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class RequestLogEntry:
    """A single structured log entry for a chat request.

    Attributes:
        request_id: Unique identifier for the request.
        timestamp: ISO-8601 timestamp of the request.
        workspace_id: The workspace the request was scoped to.
        conversation_id: The conversation the request belonged to.
        provider: The provider that produced the answer, or "" on failure.
        model: The model that produced the answer, or "" on failure.
        question: The user's question.
        retrieved_chunk_count: The number of chunks retrieved as context.
        response_time_ms: Time taken to process the request, in milliseconds.
        success: Whether the request completed successfully.
        error_message: An optional error message if the request failed.
    """

    request_id: str
    timestamp: str
    workspace_id: str
    conversation_id: str
    provider: str
    model: str
    question: str
    retrieved_chunk_count: int
    response_time_ms: float
    success: bool
    error_message: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize the entry to a JSON-friendly dict.

        Returns:
            A dict with all fields, omitting the error message when absent.
        """
        data = asdict(self)
        if data["error_message"] is None:
            data.pop("error_message")
        return data


class RequestLogger:
    """Append structured chat logs to daily JSONL files.

    Each calendar day produces one ``YYYY-MM-DD.jsonl`` file under the
    configured directory. Logging is append-only and best-effort: it never
    raises, so a logging failure can never block a chat request.
    """

    def __init__(self, log_dir: str | Path) -> None:
        """Initialize the logger, creating the directory if needed.

        Args:
            log_dir: Directory where daily JSONL log files are stored.
        """
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)

    def log(self, entry: RequestLogEntry) -> None:
        """Append a single entry to today's JSONL file.

        Args:
            entry: The structured log entry to append.
        """
        try:
            timestamp = datetime.fromisoformat(entry.timestamp)
        except (ValueError, TypeError):
            timestamp = datetime.now(timezone.utc)
        filename = f"{timestamp.date().isoformat()}.jsonl"
        path = self._log_dir / filename
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict()) + "\n")
        except OSError:
            # Logging is best-effort; never fail the request.
            return