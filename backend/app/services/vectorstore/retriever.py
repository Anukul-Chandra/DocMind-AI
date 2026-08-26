import numpy as np

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
        query_embedding: list[float] | None = None,
    ) -> list[dict]:
        """Retrieve the matching document metadata for a query and workspace.

        Args:
            query: The search query text.
            k: The number of nearest neighbors to retrieve.
            workspace_id: Only chunks belonging to this workspace are returned.
            owner_id: Only chunks owned by this user are returned. Empty for
                legacy chunks indexed before ownership was tracked.
            query_embedding: A precomputed embedding for the query, reused to
                avoid embedding the same text twice when the caller has already
                embedded it (e.g. for relevance gating). When None, the query
                is embedded here.

        Returns:
            A list of matching document metadata filtered to the workspace,
            the owner, and to non-deleted documents.
        """
        if query_embedding is None:
            query_embedding = self._embedding_service.generate_embeddings([query])[0]
        candidate_count = min(1000, 4 * k + 4)
        _, indices = self._vector_store.search(query_embedding, candidate_count)
        query_vector = np.asarray(query_embedding, dtype=np.float64)
        documents = []
        for index in indices[0]:
            if index == -1:
                continue
            document = self._metadata_store.get_document(index)
            if not self.is_eligible(document, workspace_id, owner_id):
                continue
            document["semantic_score"] = self._cosine(
                query_vector,
                self._vector_store.get_embedding(index),
            )
            documents.append(document)
            if len(documents) >= k:
                break
        return documents

    def best_similarity(
        self,
        query: str,
        workspace_id: str = DEFAULT_WORKSPACE,
        owner_id: str = "",
        query_embedding: list[float] | None = None,
    ) -> float:
        """Return the best cosine similarity of the query to an eligible chunk.

        The relevance gate for query routing: answers "how well does this
        question match anything the user has indexed?" without requiring the
        caller to inspect chunk metadata. Chunks are scoped to the workspace
        and owner, so one user's corpus never influences another user's score.

        The FAISS index stores squared L2 distances, so the query embedding is
        reconstructed from the stored vectors and compared with explicit cosine
        similarity. Only chunks matching the workspace, owner, and alive
        document status are scored.

        Args:
            query: The search query text.
            workspace_id: Only chunks belonging to this workspace are scored.
            owner_id: Only chunks owned by this user are scored.
            query_embedding: A precomputed embedding for the query, reused to
                avoid a duplicate embedding when available.

        Returns:
            The highest cosine similarity of the query against any eligible
            chunk, or 0.0 when the corpus is empty or no chunk is eligible.
        """
        if query_embedding is None:
            query_embedding = self._embedding_service.generate_embeddings([query])[0]
        if self._vector_store.ntotal == 0:
            return 0.0
        candidate_count = min(1000, self._vector_store.ntotal)
        _, indices = self._vector_store.search(query_embedding, candidate_count)
        query_vector = np.asarray(query_embedding, dtype=np.float64)
        best = 0.0
        for index in indices[0]:
            if index == -1:
                continue
            document = self._metadata_store.get_document(index)
            if not self.is_eligible(document, workspace_id, owner_id):
                continue
            similarity = self._cosine(
                query_vector,
                self._vector_store.get_embedding(index),
            )
            if similarity > best:
                best = similarity
        return best

    @staticmethod
    def _cosine(a: np.ndarray, b: list[float]) -> float:
        """Return the cosine similarity between two embedding vectors.

        Args:
            a: The first embedding vector.
            b: The second embedding vector.

        Returns:
            The cosine similarity in the range [-1, 1], or 0.0 if either
            vector has no magnitude.
        """
        vector_b = np.asarray(b, dtype=np.float64)
        norm_a = float(np.linalg.norm(a))
        norm_b = float(np.linalg.norm(vector_b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return float(np.dot(a, vector_b) / (norm_a * norm_b))

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
