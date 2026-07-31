from functools import lru_cache

from fastapi import APIRouter, Depends

from app.models.retrieve import RetrieveRequest, RetrieveResponse
from app.services.embedding import EmbeddingService
from app.services.vector_store import VectorStore
from app.services.vectorstore.metadata_store import MetadataStore
from app.services.vectorstore.retriever import Retriever

router = APIRouter()


@lru_cache
def get_retriever() -> Retriever:
    embedding_service = EmbeddingService()
    vector_store = VectorStore(embedding_service.get_embedding_dimension())
    metadata_store = MetadataStore()
    return Retriever(embedding_service, vector_store, metadata_store)


@router.post("/retrieve", response_model=RetrieveResponse)
def retrieve(request: RetrieveRequest, retriever: Retriever = Depends(get_retriever)):
    results = retriever.retrieve(request.query, k=request.k)
    return RetrieveResponse(results=results)
