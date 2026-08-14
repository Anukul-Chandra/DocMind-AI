"""Repository interfaces for the persistence layer.

Business services depend only on these abstractions so the current JSON-backed
implementations can later be replaced by PostgreSQL without changing business
logic (Dependency Inversion Principle).
"""

from abc import ABC, abstractmethod

from app.services.document_registry import Document
from app.services.logging.request_logger import RequestLogEntry


class DocumentRepository(ABC):
    """Repository for indexed document records.

    Ownership is enforced by this interface: every document operation that
    reads or mutates a user's documents is scoped to ``owner_id`` so a caller
    cannot list, retrieve, or delete another user's documents.
    """

    @abstractmethod
    def register(
        self,
        workspace_id: str,
        filename: str,
        chunk_count: int,
        owner_id: str,
        document_id: str | None = None,
    ) -> Document:
        """Register a new indexed document owned by a user.

        Args:
            workspace_id: The workspace the document belongs to.
            filename: The original document filename.
            chunk_count: The number of chunks indexed for the document.
            owner_id: The user id that owns the document.
            document_id: An explicit identifier, or None to generate one.

        Returns:
            The registered document.
        """

    @abstractmethod
    def list_documents(self, owner_id: str) -> list[Document]:
        """Return all documents owned by a user.

        Args:
            owner_id: The user id whose documents to return.

        Returns:
            A list of documents owned by the given user.
        """

    @abstractmethod
    def get_document(self, document_id: str, owner_id: str) -> Document | None:
        """Return a document by identifier if it belongs to the owner.

        Args:
            document_id: The document identifier.
            owner_id: The expected owner of the document.

        Returns:
            The matching document, or None if it is not known or belongs to
            another owner.
        """

    @abstractmethod
    def list_all_documents(self) -> list[Document]:
        """Return every registered document regardless of owner.

        This is a dedicated, read-only inventory path for audit and
        consistency tooling. It does not bypass the ownership scoping of the
        read/mutate operations above; those remain the only document path for
        application callers.

        Returns:
            A list of every registered document.
        """

    @abstractmethod
    def exists(self, document_id: str) -> bool:
        """Return whether a document identifier is registered.

        Args:
            document_id: The document identifier.

        Returns:
            True if the document exists in the repository.
        """

    @abstractmethod
    def delete_document(self, document_id: str, owner_id: str) -> bool:
        """Mark a document as deleted if it belongs to the owner.

        Args:
            document_id: The document identifier.
            owner_id: The expected owner of the document.

        Returns:
            True if the document was found, owned by the caller, and marked
            deleted.
        """

    @abstractmethod
    def is_deleted(self, document_id: str) -> bool:
        """Return whether a document is marked deleted.

        Args:
            document_id: The document identifier.

        Returns:
            True if the document is marked deleted or unknown.
        """


class WorkspaceRepository(ABC):
    """Repository for workspace identifiers."""

    @abstractmethod
    def list_workspaces(self) -> list[str]:
        """Return all known workspace identifiers.

        Returns:
            A list of workspace identifiers.
        """


class ConversationRepository(ABC):
    """Repository for in-memory conversation history."""

    @abstractmethod
    def create_conversation(self) -> str:
        """Create a new empty conversation.

        Returns:
            An identifier for the new conversation.
        """

    @abstractmethod
    def get_history(self, conversation_id: str) -> list[dict[str, str]]:
        """Return the stored message history for a conversation.

        Args:
            conversation_id: The conversation identifier.

        Returns:
            The message history, or an empty list if unknown.
        """

    @abstractmethod
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


class LogRepository(ABC):
    """Repository for structured request log entries."""

    @abstractmethod
    def log(self, entry: RequestLogEntry) -> None:
        """Persist a single structured log entry.

        Args:
            entry: The log entry to persist.
        """
