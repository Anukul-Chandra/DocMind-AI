from functools import lru_cache

from app.core.config import settings
from app.services.chat import ChatService
from app.services.embedding import EmbeddingService
from app.services.indexing import DocumentIndexService
from app.services.llm.factory import build_provider_manager
from app.services.llm.prompt_builder import PromptBuilder
from app.services.vector_store import VectorStore
from app.services.vectorstore.metadata_store import MetadataStore
from app.services.vectorstore.retriever import Retriever


@lru_cache
def get_embedding_service() -> EmbeddingService:
    return EmbeddingService()


@lru_cache
def get_vector_store() -> VectorStore:
    store = VectorStore(get_embedding_service().get_embedding_dimension())
    store.load_index(settings.faiss_index_path)
    return store


@lru_cache
def get_metadata_store() -> MetadataStore:
    store = MetadataStore()
    store.load(settings.metadata_path)
    return store


@lru_cache
def get_document_index_service() -> DocumentIndexService:
    return DocumentIndexService(
        get_embedding_service(),
        get_vector_store(),
        get_metadata_store(),
    )


@lru_cache
def get_retriever() -> Retriever:
    return Retriever(
        get_embedding_service(),
        get_vector_store(),
        get_metadata_store(),
    )


@lru_cache
def get_chat_service() -> ChatService:
    return ChatService(
        get_retriever(),
        PromptBuilder(),
        build_provider_manager(),
    )
