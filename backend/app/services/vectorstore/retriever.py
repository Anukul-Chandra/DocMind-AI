from app.repositories.interfaces import DocumentRepository
from app.services.embedding import EmbeddingService
from app.services.retrieval.base import Retriever
from app.services.vector_store import VectorStore
from app.services.vectorstore.metadata_store import MetadataStore
from app.services.vectorstore.workspace import DEFAULT_WORKSPACE


class SemanticRetriever(Retriever):
    """Retrieve relevant document chunks for a query using embeddings and FAISS."""

    def __init__(
        self,
        embedding_service: EmbeddingService,
        vector_store: VectorStore,
        metadata_store: MetadataStore,
        document_registry: DocumentRepository | None = None,
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
        owner_id: str = "",
    ) -> list[dict]:
        """Retrieve the matching document metadata for a query and workspace.

        Args:
            query: The search query text.
            k: The number of nearest neighbors to retrieve.
            workspace_id: Only chunks belonging to this workspace are returned.
            owner_id: Only chunks owned by this user are returned. Empty for
                legacy chunks indexed before ownership was tracked.

        Returns:
            A list of matching document metadata filtered to the workspace,
            the owner, and to non-deleted documents.
        """
        query_embedding = self._embedding_service.generate_embeddings([query])[0]
        candidate_count = min(1000, 4 * k + 4)
        _, indices = self._vector_store.search(query_embedding, candidate_count)
        documents = []
        for index in indices[0]:
            if index == -1:
                continue
            document = self._metadata_store.get_document(index)
            if not self.is_eligible(document, workspace_id, owner_id):
                continue
            documents.append(document)
            if len(documents) >= k:
                break
        return documents

    def is_eligible(
        self,
        document: dict,
        workspace_id: str,
        owner_id: str = "",
    ) -> bool:
        """Return whether a chunk should be returned for the workspace and owner.

        Args:
            document: The chunk metadata to check.
            workspace_id: The requested workspace.
            owner_id: The requested owner. Empty for legacy ownerless chunks.

        Returns:
            True if the chunk belongs to the workspace and owner and its
            document is not deleted. Otherwise False.
        """
        if document["workspace_id"] != workspace_id:
            return False
        if document.get("owner_id", "") != owner_id:
            return False
        document_id = document.get("document_id")
        if document_id and self._document_registry is not None:
            return not self._document_registry.is_deleted(document_id)
        return True
