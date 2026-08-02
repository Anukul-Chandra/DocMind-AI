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
        document_id: str | None = None,
    ) -> Document:
        """Register a new indexed document.

        Args:
            workspace_id: The workspace the document belongs to.
            filename: The original document filename.
            chunk_count: The number of chunks indexed for the document.
            document_id: An explicit identifier, or None to generate one.

        Returns:
            The registered document.
        """
        return self._registry.register(
            workspace_id,
            filename,
            chunk_count,
            document_id,
        )

    def list_documents(self) -> list[Document]:
        """Return all registered documents.

        Returns:
            A list of all tracked documents.
        """
        return self._registry.list_documents()

    def get_document(self, document_id: str) -> Document | None:
        """Return a document by its identifier.

        Args:
            document_id: The document identifier.

        Returns:
            The matching document, or None if it is not known.
        """
        return self._registry.get_document(document_id)

    def exists(self, document_id: str) -> bool:
        """Return whether a document identifier is registered.

        Args:
            document_id: The document identifier.

        Returns:
            True if the document exists in the repository.
        """
        return self._registry.exists(document_id)

    def delete_document(self, document_id: str) -> bool:
        """Mark a document as deleted.

        Args:
            document_id: The document identifier.

        Returns:
            True if the document was found and marked deleted.
        """
        return self._registry.delete_document(document_id)

    def is_deleted(self, document_id: str) -> bool:
        """Return whether a document is marked deleted.

        Args:
            document_id: The document identifier.

        Returns:
            True if the document is marked deleted or unknown.
        """
        return self._registry.is_deleted(document_id)
