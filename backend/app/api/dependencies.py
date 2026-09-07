from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, Header, HTTPException, Request, status

from app.core.config import settings


@lru_cache
def get_embedding_service():
    from app.services.embedding import EmbeddingService
    return EmbeddingService()


@lru_cache
def get_vector_store():
    from app.services.vector_store import VectorStore
    return VectorStore(
        get_embedding_service().get_embedding_dimension(),
        index_path=settings.faiss_index_path,
    )


@lru_cache
def get_metadata_store():
    from app.services.vectorstore.metadata_store import MetadataStore
    return MetadataStore(path=settings.metadata_path)


@lru_cache
def get_document_service():
    from app.services.document import (
        Chunker,
        DocumentClassifier,
        DocumentService,
        PDFProcessor,
    )
    from app.services.document.extraction import ExtractionService
    from app.services.llm.factory import build_provider_manager

    return DocumentService(
        PDFProcessor(),
        Chunker(),
        get_embedding_service(),
        get_vector_store(),
        get_metadata_store(),
        faiss_index_path=settings.faiss_index_path,
        metadata_path=settings.metadata_path,
        classifier=DocumentClassifier(),
        extractor=ExtractionService(build_provider_manager()),
    )


@lru_cache
def get_document_registry():
    from app.services.document_registry import DocumentRegistry
    return DocumentRegistry(settings.documents_path)


@lru_cache
def get_document_repository():
    if settings.persistence_backend == "postgres":
        from app.db.session import get_session_factory
        from app.repositories.postgres.document_repository import (
            PostgresDocumentRepository,
        )
        return PostgresDocumentRepository(get_session_factory())
    from app.repositories.json.document_repository import JsonDocumentRepository
    return JsonDocumentRepository(get_document_registry())


@lru_cache
def get_user_repository():
    if settings.persistence_backend == "postgres":
        from app.db.session import get_session_factory
        from app.repositories.postgres.user_repository import PostgresUserRepository
        return PostgresUserRepository(get_session_factory())
    from app.repositories.json.user_repository import JsonUserRepository
    return JsonUserRepository(settings.users_path)


@lru_cache
def get_conversation_repository():
    if settings.persistence_backend == "postgres":
        from app.db.session import get_session_factory
        from app.repositories.postgres.conversation_repository import (
            PostgresConversationRepository,
        )
        return PostgresConversationRepository(get_session_factory())
    from app.repositories.json.conversation_repository import JsonConversationRepository
    from app.services.chat.memory import ConversationMemory
    return JsonConversationRepository(ConversationMemory(settings.conversations_path))


@lru_cache
def get_conversations_service():
    from app.services.chat.conversations_service import ConversationsService
    return ConversationsService(get_conversation_repository())


@lru_cache
def get_auth_service():
    from app.services.auth import AuthService, JWTService, PasswordService
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
def get_log_repository():
    if settings.persistence_backend == "postgres":
        from app.db.session import get_session_factory
        from app.repositories.postgres.log_repository import PostgresLogRepository
        return PostgresLogRepository(get_session_factory())
    from app.repositories.json.log_repository import JsonLogRepository
    from app.services.logging.request_logger import RequestLogger
    return JsonLogRepository(RequestLogger(settings.logs_dir))


_GENERIC_AUTH_FAILURE = "Invalid or missing authentication token."


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) != 2:
        return None
    scheme, token = parts
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def get_current_user(
    request: Request,
    authorization: str | None = Header(None),
    auth_service = Depends(get_auth_service),
):
    from app.services.auth import AuthenticationError

    token = _extract_bearer_token(authorization)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_GENERIC_AUTH_FAILURE,
        )
    try:
        user = auth_service.get_user_from_access_token(token)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_GENERIC_AUTH_FAILURE,
        ) from exc
    request.state.user_id = user.user_id
    return user


@lru_cache
def get_semantic_retriever():
    from app.services.vectorstore.retriever import SemanticRetriever
    return SemanticRetriever(
        get_embedding_service(),
        get_vector_store(),
        get_metadata_store(),
        get_document_repository(),
    )


@lru_cache
def get_retriever():
    from app.services.retrieval.hybrid_retriever import HybridRetriever
    return HybridRetriever(
        semantic_retriever=get_semantic_retriever(),
        bm25_retriever=get_bm25_retriever(),
    )


@lru_cache
def get_bm25_retriever():
    from app.services.retrieval.bm25_retriever import BM25Retriever
    return BM25Retriever(
        get_metadata_store(),
        get_document_repository(),
    )


@lru_cache
def get_query_router():
    from app.services.chat.query_router import QueryRouter

    semantic_retriever = get_semantic_retriever()
    bm25_retriever = get_bm25_retriever()

    def _relevance_score(
        question: str,
        owner_id: str,
        query_embedding: list[float] | None,
    ) -> float:
        return semantic_retriever.best_similarity(
            question,
            owner_id=owner_id,
            query_embedding=query_embedding,
        )

    def _lexical_score(question: str, owner_id: str) -> float:
        return bm25_retriever.best_score(question, owner_id=owner_id)

    return QueryRouter(
        get_embedding_service(),
        relevance_scorer=_relevance_score,
        lexical_scorer=_lexical_score,
        personal_floor=settings.rag_personal_floor,
        topic_threshold=settings.rag_topic_threshold,
        docnoun_floor=settings.rag_docnoun_floor,
    )


@lru_cache
def get_chat_service():
    from app.services.chat.chat_service import ChatService
    from app.services.llm.factory import build_provider_manager
    from app.services.llm.prompt_builder import PromptBuilder
    from app.services.rag.query_rewriter import QueryRewriter
    from app.services.rag.retrieval_evaluator import RetrievalEvaluator

    provider_manager = build_provider_manager()
    return ChatService(
        get_retriever(),
        PromptBuilder(),
        provider_manager,
        document_repository=get_document_repository(),
        query_router=get_query_router(),
        retrieval_evaluator=RetrievalEvaluator(),
        query_rewriter=QueryRewriter(provider_manager),
        conversation_repository=get_conversation_repository(),
    )
