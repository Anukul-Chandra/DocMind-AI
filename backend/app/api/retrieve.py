from fastapi import APIRouter, Depends

from app.api.dependencies import get_retriever as get_shared_retriever
from app.models.responses import SuccessResponse
from app.models.retrieve import RetrieveRequest, RetrieveResponse
from app.services.retrieval import Retriever

router = APIRouter()


@router.post("/retrieve", response_model=SuccessResponse[RetrieveResponse])
def retrieve(
    request: RetrieveRequest,
    retriever: Retriever = Depends(get_shared_retriever),
) -> SuccessResponse[RetrieveResponse]:
    """Retrieve the most relevant document chunks for a query.

    Args:
        request: The retrieval request with the query and result count.
        retriever: The retriever used to find relevant chunks.

    Returns:
        A success envelope with the retrieved chunks.
    """
    results = retriever.retrieve(request.query, k=request.k)
    return SuccessResponse(data=RetrieveResponse(results=results))
