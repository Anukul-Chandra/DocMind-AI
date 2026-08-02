from app.services.embedding import EmbeddingService
from app.services.vector_store import VectorStore
from app.services.vectorstore.metadata_store import MetadataStore
from app.services.vectorstore.workspace import DEFAULT_WORKSPACE


class Retriever:
    """Retrieve relevant document chunks for a query using embeddings and FAISS."""

    def __init__(
        self,
        embedding_service: EmbeddingService,
        vector_store: VectorStore,
        metadata_store: MetadataStore,
    ) -> None:
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
            A list of matching document metadata filtered to the workspace.
        """
        query_embedding = self._embedding_service.generate_embeddings([query])[0]
        _, indices = self._vector_store.search(query_embedding, k)
        documents = []
        for index in indices[0]:
            if index == -1:
                continue
            document = self._metadata_store.get_document(index)
            if document["workspace_id"] == workspace_id:
                documents.append(document)
        return documents
