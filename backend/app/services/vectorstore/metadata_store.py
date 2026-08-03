from app.services.storage import JsonFileStore
from app.services.vectorstore.workspace import DEFAULT_WORKSPACE


class MetadataStore:
    """Store document chunk metadata in the order they are added."""

    def __init__(self) -> None:
        self.documents: list[dict] = []

    def add_documents(
        self,
        texts: list[str],
        filename: str,
        workspace_id: str = DEFAULT_WORKSPACE,
        document_id: str | None = None,
    ) -> None:
        """Store document chunks with sequential ids starting from 1.

        Args:
            texts: The document text chunks.
            filename: The source document's filename.
            workspace_id: The workspace the document belongs to.
            document_id: The identifier of the owning document, or None.
        """
        document_id = document_id or ""
        start_id = len(self.documents) + 1
        for offset, text in enumerate(texts):
            self.documents.append(
                {
                    "id": start_id + offset,
                    "workspace_id": workspace_id,
                    "filename": filename,
                    "chunk_id": offset + 1,
                    "document_id": document_id,
                    "text": text,
                }
            )

    def get_document(self, index: int) -> dict:
        """Return the stored document for a given index.

        Args:
            index: The index of the stored document.

        Returns:
            The stored document.

        Raises:
            IndexError: If the index is out of range.
        """
        if index < 0 or index >= len(self.documents):
            raise IndexError("document index out of range")
        return self.documents[index]

    def get_all_documents(self) -> list[dict]:
        """Return all stored documents.

        Returns:
            A list of all stored documents.
        """
        return self.documents

    def save(self, path: str) -> None:
        """Persist all metadata to disk as pretty-printed JSON.

        Args:
            path: The file path to save the metadata to.
        """
        JsonFileStore.save(path, self.documents)

    def load(self, path: str) -> None:
        """Restore metadata from disk, or start empty if the file is missing.

        Args:
            path: The file path to load the metadata from.
        """
        self.documents = JsonFileStore.load(path, default=[])
