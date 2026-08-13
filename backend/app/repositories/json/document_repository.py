"""JSON-backed implementation of the DocumentRepository interface."""

from app.repositories.interfaces import DocumentRepository
from app.services.document_registry import Document, DocumentRegistry


class JsonDocumentRepository(DocumentRepository):
    """JSON-backed document repository.

    Delegates to the existing :class:`DocumentRegistry` so callers depend only
    on the :class:`DocumentRepository` interface.
    """

    def __init__(self, registry: DocumentRegistry) -> None:
        """Initialize the repository with a JSON document registry.

        Args:
            registry: The backing document registry.
        """
        self._registry = registry

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
        return self._registry.register(
            workspace_id,
            filename,
            chunk_count,
            owner_id,
            document_id,
        )

    def list_documents(self, owner_id: str) -> list[Document]:
        """Return all documents owned by a user.

        Args:
            owner_id: The user id whose documents to return.

        Returns:
            A list of documents owned by the given user.
        """
        return self._registry.list_documents(owner_id)

    def get_document(self, document_id: str, owner_id: str) -> Document | None:
        """Return a document by identifier if it belongs to the owner.

        Args:
            document_id: The document identifier.
            owner_id: The expected owner of the document.

        Returns:
            The matching document, or None if it is not known or belongs to
            another owner.
        """
        return self._registry.get_document(document_id, owner_id)

    def exists(self, document_id: str) -> bool:
        """Return whether a document identifier is registered.

        Args:
            document_id: The document identifier.

        Returns:
            True if the document exists in the repository.
        """
        return self._registry.exists(document_id)

    def delete_document(self, document_id: str, owner_id: str) -> bool:
        """Mark a document as deleted if it belongs to the owner.

        Args:
            document_id: The document identifier.
            owner_id: The expected owner of the document.

        Returns:
            True if the document was found, owned by the caller, and marked
            deleted.
        """
        return self._registry.delete_document(document_id, owner_id)

    def is_deleted(self, document_id: str) -> bool:
        """Return whether a document is marked deleted.

        Args:
            document_id: The document identifier.

        Returns:
            True if the document is marked deleted or unknown.
        """
        return self._registry.is_deleted(document_id)
