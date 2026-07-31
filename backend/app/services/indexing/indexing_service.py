from app.core.config import FAISS_INDEX_PATH, METADATA_PATH
from app.services.embedding import EmbeddingService
from app.services.vector_store import VectorStore
from app.services.vectorstore.metadata_store import MetadataStore


class IndexingService:
    """Orchestrate document indexing across embedding, vector, and metadata stores."""

    def __init__(
        self,
        embedding_service: EmbeddingService,
        vector_store: VectorStore,
        metadata_store: MetadataStore,
    ) -> None:
        self._embedding_service = embedding_service
        self._vector_store = vector_store
        self._metadata_store = metadata_store

    def index_document(self, chunks: list[str], filename: str) -> None:
        """Embed, store, and persist a document's chunks.

        Args:
            chunks: The document text chunks.
            filename: The source document's filename.
        """
        embeddings = self._embedding_service.generate_embeddings(chunks)
        self._vector_store.add_embeddings(embeddings)
        self._metadata_store.add_documents(chunks, filename)
        self._vector_store.save(FAISS_INDEX_PATH)
        self._metadata_store.save(METADATA_PATH)
