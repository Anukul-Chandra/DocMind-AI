from functools import lru_cache

from app.core.config import settings
from app.repositories import (
    ConversationRepository,
    DocumentRepository,
    JsonConversationRepository,
    JsonDocumentRepository,
    JsonLogRepository,
    JsonWorkspaceRepository,
    LogRepository,
    WorkspaceRepository,
)
from app.services.chat import ChatService
from app.services.chat.chat_service import ChatService as RagChatService
from app.services.chat.memory import ConversationMemory
from app.services.document_registry import DocumentRegistry
from app.services.embedding import EmbeddingService
from app.services.indexing import DocumentIndexService
from app.services.llm.factory import build_provider_manager
from app.services.llm.prompt_builder import PromptBuilder
from app.services.logging import RequestLogger
from app.services.retrieval import BM25Retriever, HybridRetriever, Retriever
from app.services.vector_store import VectorStore
from app.services.vectorstore.metadata_store import MetadataStore
from app.services.vectorstore.retriever import SemanticRetriever


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
def get_document_registry() -> DocumentRegistry:
    return DocumentRegistry(settings.documents_path)


@lru_cache
def get_document_repository() -> DocumentRepository:
    return JsonDocumentRepository(get_document_registry())


@lru_cache
def get_workspace_repository() -> WorkspaceRepository:
    return JsonWorkspaceRepository(get_document_repository())


@lru_cache
def get_retriever() -> Retriever:
    return HybridRetriever(
        semantic_retriever=SemanticRetriever(
            get_embedding_service(),
            get_vector_store(),
            get_metadata_store(),
            get_document_repository(),
        ),
        bm25_retriever=BM25Retriever(
            get_metadata_store(),
            get_document_repository(),
        ),
    )


@lru_cache
def get_request_logger() -> RequestLogger:
    return RequestLogger(settings.logs_dir)


@lru_cache
def get_log_repository() -> LogRepository:
    return JsonLogRepository(get_request_logger())


@lru_cache
def get_conversation_repository() -> ConversationRepository:
    return JsonConversationRepository(ConversationMemory())


@lru_cache
def get_chat_service() -> ChatService:
    return ChatService(
        get_retriever(),
        PromptBuilder(),
        build_provider_manager(),
        get_conversation_repository(),
        get_log_repository(),
    )


@lru_cache
def get_rag_chat_service() -> RagChatService:
    return RagChatService(
        get_retriever(),
        PromptBuilder(),
        build_provider_manager(),
    )
