from app.core.config import settings
from app.services.vector_store import VectorStore
from app.services.vectorstore.metadata_store import MetadataStore


class StorageManager:
    """Load and restore application storage on startup."""

    def __init__(
        self,
        vector_store: VectorStore,
        metadata_store: MetadataStore,
    ) -> None:
        self._vector_store = vector_store
        self._metadata_store = metadata_store

    def initialize(self) -> None:
        """Load stored index and metadata, or start with empty stores."""
        self._vector_store.load_index(settings.faiss_index_path)
        self._metadata_store.load(settings.metadata_path)
