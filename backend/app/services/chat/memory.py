"""File-backed JSON conversation memory for the chat pipeline."""

import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.services.chat_domain import ConversationMessage, ConversationMeta
from app.services.storage import JsonFileStore

#: Maximum number of message pairs kept per conversation.
CONVERSATION_LIMIT = 10

#: Maximum characters used for the auto-generated conversation title.
TITLE_MAX_LENGTH = 60


class ConversationMemory:
    """Store per-user conversation history in a single JSON file.

    Each conversation belongs to exactly one ``owner_id`` and keeps a bounded
    sliding window of the most recent user/assistant message pairs. Data is
    persisted to disk via :class:`JsonFileStore` (atomic writes, auto-created
    parents), so history survives server restarts. Ownership is enforced on
    every operation: unknown or not-owned conversations read as empty and
    mutate operations are no-ops.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        """Initialize the store, optionally loading an existing file.

        Args:
            path: Filesystem path to the JSON storage file. When None, the
                store is memory-only (used by tests).
        """
        self._path = Path(path) if path is not None else None
        #: conversation_id -> {"owner_id", "title", "created_at", "updated_at",
        #:                    "messages": [{"role", "content", "created_at"}]}
        self._conversations: dict[str, dict] = {}
        self._load()

    def create_conversation(self, owner_id: str) -> str:
        """Create a new empty conversation owned by a user.

        Args:
            owner_id: The user id that owns the conversation.

        Returns:
            A UUID string identifying the new conversation.
        """
        conversation_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self._conversations[conversation_id] = {
            "owner_id": owner_id,
            "title": None,
            "created_at": now,
            "updated_at": now,
            "messages": [],
        }
        self._save()
        return conversation_id

    def list_conversations(self, owner_id: str) -> list[ConversationMeta]:
        """Return all conversations owned by a user, newest first.

        Args:
            owner_id: The user id whose conversations to return.

        Returns:
            A list of conversation summaries owned by the user.
        """
        rows = [
            self._to_meta(conversation_id, record)
            for conversation_id, record in self._conversations.items()
            if record["owner_id"] == owner_id
        ]
        rows.sort(key=lambda meta: meta.updated_at or "", reverse=True)
        return rows

    def get_conversation(
        self, conversation_id: str, owner_id: str
    ) -> ConversationMeta | None:
        """Return a conversation if it belongs to the owner.

        Args:
            conversation_id: The conversation identifier.
            owner_id: The expected owner of the conversation.

        Returns:
            The matching conversation summary, or None if it is unknown or
            belongs to another owner.
        """
        record = self._get_owned(conversation_id, owner_id)
        return self._to_meta(conversation_id, record) if record is not None else None

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
        record = self._get_owned(conversation_id, owner_id)
        if record is None:
            return []
        return [
            ConversationMessage(
                role=message["role"],
                content=message["content"],
                conversation_id=conversation_id,
            )
            for message in record.get("messages", [])
        ]

    def add_exchange(
        self,
        conversation_id: str,
        owner_id: str,
        user_message: str,
        assistant_response: str,
    ) -> None:
        """Record a user/assistant exchange, trimming to the latest pairs.

        Sets the conversation title from the first user message when it is
        still untitled. Exchanges for a conversation that belongs to another
        owner are ignored.

        Args:
            conversation_id: The conversation identifier.
            owner_id: The user id that owns the conversation.
            user_message: The user's question.
            assistant_response: The assistant's answer.
        """
        record = self._get_owned(conversation_id, owner_id)
        if record is None:
            return
        now = datetime.now(timezone.utc).isoformat()
        if record.get("title") is None:
            record["title"] = self._derive_title(user_message)
        messages: list[dict] = record.setdefault("messages", [])
        messages.append({"role": "user", "content": user_message, "created_at": now})
        messages.append(
            {"role": "assistant", "content": assistant_response, "created_at": now}
        )
        self._trim(messages)
        record["updated_at"] = now
        self._save()

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
        record = self._get_owned(conversation_id, owner_id)
        if record is None:
            return False
        record["title"] = title
        record["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save()
        return True

    def delete_conversation(self, conversation_id: str, owner_id: str) -> bool:
        """Delete a conversation if owned by the caller.

        Args:
            conversation_id: The conversation identifier.
            owner_id: The expected owner of the conversation.

        Returns:
            True if the conversation was found, owned by the caller, and
            deleted.
        """
        record = self._get_owned(conversation_id, owner_id)
        if record is None:
            return False
        del self._conversations[conversation_id]
        self._save()
        return True

    def _get_owned(
        self, conversation_id: str, owner_id: str
    ) -> dict | None:
        """Return a record if it exists and belongs to the owner.

        Args:
            conversation_id: The conversation identifier.
            owner_id: The expected owner of the conversation.

        Returns:
            The stored record, or None if unknown or not owned.
        """
        record = self._conversations.get(conversation_id)
        if record is None or record.get("owner_id") != owner_id:
            return None
        return record

    @staticmethod
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

    @staticmethod
    def _to_meta(conversation_id: str, record: dict) -> ConversationMeta:
        """Convert a stored record to a conversation summary.

        Args:
            conversation_id: The conversation identifier.
            record: The raw stored conversation record.

        Returns:
            A :class:`ConversationMeta` representing the record.
        """
        return ConversationMeta(
            conversation_id=conversation_id,
            owner_id=record.get("owner_id", ""),
            title=record.get("title"),
            created_at=_parse_dt(record.get("created_at")),
            updated_at=_parse_dt(record.get("updated_at")),
            message_count=len(record.get("messages", [])),
        )

    def _load(self) -> None:
        """Load conversations from the storage file when present."""
        if self._path is None:
            return
        data = JsonFileStore.load(self._path, default=[])
        for item in data:
            conversation_id = item.get("id")
            if not conversation_id:
                continue
            record = {
                "owner_id": item.get("owner_id", ""),
                "title": item.get("title"),
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at"),
                "messages": item.get("messages", []),
            }
            self._conversations[conversation_id] = record

    def _save(self) -> None:
        """Persist the in-memory conversations to the JSON storage file."""
        if self._path is None:
            return
        data = [
            {
                "id": conversation_id,
                "owner_id": record["owner_id"],
                "title": record["title"],
                "created_at": record["created_at"],
                "updated_at": record["updated_at"],
                "messages": record["messages"],
            }
            for conversation_id, record in self._conversations.items()
        ]
        JsonFileStore.save(self._path, data)

    @staticmethod
    def _trim(messages: list[dict]) -> None:
        """Keep only the most recent messages within the configured window.

        Args:
            messages: The message list to trim in place.
        """
        max_messages = CONVERSATION_LIMIT * 2
        if len(messages) > max_messages:
            del messages[: len(messages) - max_messages]


def _parse_dt(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp string into a timezone-aware datetime.

    Args:
        value: The timestamp string, or None.

    Returns:
        A timezone-aware datetime, or None when the value is absent.
    """
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
