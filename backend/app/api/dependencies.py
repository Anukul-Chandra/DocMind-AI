from functools import lru_cache

from app.core.config import settings
from app.db.session import get_session_factory
from app.repositories import (
    DocumentRepository,
    JsonDocumentRepository,
    JsonUserRepository,
    PostgresUserRepository,
)
from app.services.auth import AuthService, JWTService, PasswordService, UserRepository
from app.services.chat.chat_service import ChatService
from app.services.document import Chunker, DocumentService, PDFProcessor
from app.services.document_registry import DocumentRegistry
from app.services.embedding import EmbeddingService
from app.services.llm.factory import build_provider_manager
from app.services.llm.prompt_builder import PromptBuilder
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
def get_document_service() -> DocumentService:
    return DocumentService(
        PDFProcessor(),
        Chunker(),
        get_embedding_service(),
        get_vector_store(),
        get_metadata_store(),
        faiss_index_path=settings.faiss_index_path,
        metadata_path=settings.metadata_path,
    )


@lru_cache
def get_document_registry() -> DocumentRegistry:
    return DocumentRegistry(settings.documents_path)


@lru_cache
def get_document_repository() -> DocumentRepository:
    return JsonDocumentRepository(get_document_registry())


@lru_cache
def get_user_repository() -> UserRepository:
    """Return the UserRepository selected by the configured persistence backend.

    ``persistence_backend`` of ``"json"`` (the default) uses the JSON store;
    ``"postgres"`` uses the SQLAlchemy-backed repository. AuthService only ever
    sees the resulting repository, never the backend.
    """
    if settings.persistence_backend == "postgres":
        return PostgresUserRepository(get_session_factory())
    return JsonUserRepository(settings.users_path)


@lru_cache
def get_auth_service() -> AuthService:
    """Return the AuthService bound to the configured user repository.

    The service receives the repository selected by ``get_user_repository``,
    so it never knows whether persistence is JSON or PostgreSQL.
    """
    return AuthService(
        users=get_user_repository(),
        passwords=PasswordService(),
        tokens=JWTService(
            secret_key=settings.jwt_secret,
            algorithm=settings.jwt_algorithm,
            access_ttl_seconds=settings.jwt_access_ttl_seconds,
            refresh_ttl_seconds=settings.jwt_refresh_ttl_seconds,
        ),
    )


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
def get_chat_service() -> ChatService:
    return ChatService(
        get_retriever(),
        PromptBuilder(),
        build_provider_manager(),
    )
