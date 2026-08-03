"""Document model and in-memory/JSON registry for indexed documents."""

import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from app.services.storage import JsonFileStore


class Document(BaseModel):
    """A registered, indexed document within a workspace.

    Attributes:
        document_id: Unique identifier for the document.
        workspace_id: The workspace the document belongs to.
        filename: The original filename.
        uploaded_at: When the document was tracked.
        chunk_count: Number of chunks produced for this document.
        deleted: Whether the document has been marked as deleted.
    """

    document_id: str
    workspace_id: str
    filename: str
    uploaded_at: datetime
    chunk_count: int
    deleted: bool = False


class DocumentRegistry:
    """Track indexed documents and their deletion status.

    Persists to a single JSON file. Vectors are not removed from FAISS on
    deletion; the document is only marked as deleted in this registry.
    """

    def __init__(self, path: str | Path) -> None:
        """Initialize the registry and load any existing documents.

        Args:
            path: Filesystem path to the JSON storage file.
        """
        self._path = Path(path)
        self._documents: dict[str, Document] = {}
        self._load()

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
            chunk_count: Number of chunks indexed for the document.
            document_id: An explicit identifier, or None to generate one.

        Returns:
            The registered document.
        """
        document_id = document_id or str(uuid.uuid4())
        document = Document(
            document_id=document_id,
            workspace_id=workspace_id,
            filename=filename,
            uploaded_at=datetime.now(timezone.utc),
            chunk_count=chunk_count,
        )
        self._documents[document_id] = document
        self._save()
        return document

    def list_documents(self) -> list[Document]:
        """Return all registered documents.

        Returns:
            A list of all tracked documents.
        """
        return list(self._documents.values())

    def get_document(self, document_id: str) -> Document | None:
        """Return a document by its identifier.

        Args:
            document_id: The document identifier.

        Returns:
            The matching document, or None if it is not known.
        """
        return self._documents.get(document_id)

    def exists(self, document_id: str) -> bool:
        """Check whether a document identifier is registered.

        Args:
            document_id: The document identifier.

        Returns:
            True if the document exists in the registry.
        """
        return document_id in self._documents

    def delete_document(self, document_id: str) -> bool:
        """Mark a document as deleted.

        The associated FAISS vectors are not removed; the document is only
        marked so that retrieval and chat ignore it.

        Args:
            document_id: The document identifier.

        Returns:
            True if the document was found and marked deleted, otherwise False.
        """
        document = self._documents.get(document_id)
        if document is None or document.deleted:
            return False
        self._documents[document_id] = document.model_copy(
            update={"deleted": True}
        )
        self._save()
        return True

    def is_deleted(self, document_id: str) -> bool:
        """Return whether a document identifier is marked deleted.

        Args:
            document_id: The document identifier.

        Returns:
            True if the document is marked deleted or unknown, otherwise False.
        """
        document = self._documents.get(document_id)
        return bool(document and document.deleted)

    def _save(self) -> None:
        """Persist the registry to the JSON storage file."""
        data = [document.model_dump(mode="json") for document in self._documents.values()]
        JsonFileStore.save(self._path, data)

    def _load(self) -> None:
        """Load documents from the JSON storage file, starting empty if missing."""
        data = JsonFileStore.load(self._path, default=[])
        self._documents = {
            item["document_id"]: Document(**item) for item in data
        }