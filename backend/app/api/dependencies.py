from functools import lru_cache

from app.services.chat import ChatService
from app.services.embedding import EmbeddingService
from app.services.indexing import IndexingService
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
    return VectorStore(get_embedding_service().get_embedding_dimension())


@lru_cache
def get_metadata_store() -> MetadataStore:
    return MetadataStore()


@lru_cache
def get_indexing_service() -> IndexingService:
    return IndexingService(
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
