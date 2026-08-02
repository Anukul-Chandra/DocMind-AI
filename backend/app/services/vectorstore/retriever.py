from typing import Protocol

from app.services.embedding import EmbeddingService
from app.services.retrieval.base import Retriever
from app.services.vector_store import VectorStore
from app.services.vectorstore.metadata_store import MetadataStore
from app.services.vectorstore.workspace import DEFAULT_WORKSPACE


class DeletionAwareRegistry(Protocol):
    """Minimal structural interface for a deletions registry."""

    def is_deleted(self, document_id: str) -> bool:
        """Return whether a document is marked as deleted."""


class SemanticRetriever(Retriever):
    """Retrieve relevant document chunks for a query using embeddings and FAISS."""

    def __init__(
        self,
        embedding_service: EmbeddingService,
        vector_store: VectorStore,
        metadata_store: MetadataStore,
        document_registry: DeletionAwareRegistry | None = None,
    ) -> None:
        self._document_registry = document_registry
        self._embedding_service = embedding_service
        self._vector_store = vector_store
        self._metadata_store = metadata_store

    def retrieve(
        self,
        query: str,
        k: int = 5,
        workspace_id: str = DEFAULT_WORKSPACE,
    ) -> list[dict]:
        """Retrieve the matching document metadata for a query and workspace.

        Args:
            query: The search query text.
            k: The number of nearest neighbors to retrieve.
            workspace_id: Only chunks belonging to this workspace are returned.

        Returns:
            A list of matching document metadata filtered to the workspace and
            to non-deleted documents.
        """
        query_embedding = self._embedding_service.generate_embeddings([query])[0]
        _, indices = self._vector_store.search(query_embedding, k)
        documents = []
        for index in indices[0]:
            if index == -1:
                continue
            document = self._metadata_store.get_document(index)
            if not self.is_eligible(document, workspace_id):
                continue
            documents.append(document)
        return documents

    def is_eligible(self, document: dict, workspace_id: str) -> bool:
        """Return whether a chunk should be returned for the workspace.

        Args:
            document: The chunk metadata to check.
            workspace_id: The requested workspace.

        Returns:
            True if the chunk belongs to the workspace and its document is not
            deleted.
        """
        if document["workspace_id"] != workspace_id:
            return False
        document_id = document.get("document_id")
        if document_id and self._document_registry is not None:
            return not self._document_registry.is_deleted(document_id)
        return True
