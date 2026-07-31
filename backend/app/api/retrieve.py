from fastapi import APIRouter, Depends

from app.api.dependencies import get_retriever as get_shared_retriever
from app.models.retrieve import RetrieveRequest, RetrieveResponse
from app.services.vectorstore.retriever import Retriever

router = APIRouter()


@router.post("/retrieve", response_model=RetrieveResponse)
def retrieve(request: RetrieveRequest, retriever: Retriever = Depends(get_shared_retriever)):
    results = retriever.retrieve(request.query, k=request.k)
    return RetrieveResponse(results=results)
