from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import (
    get_current_user,
    get_retriever as get_shared_retriever,
)
from app.models.responses import SuccessResponse
from app.models.retrieve import RetrieveRequest, RetrieveResponse
from app.services.auth import User
from app.services.retrieval import Retriever

router = APIRouter()


@router.post("/retrieve", response_model=SuccessResponse[RetrieveResponse])
def retrieve(
    request: RetrieveRequest,
    current_user: User = Depends(get_current_user),
    retriever: Retriever = Depends(get_shared_retriever),
) -> SuccessResponse[RetrieveResponse]:
    """Retrieve the most relevant document chunks owned by the user.

    Authentication is required and the authenticated user's id is passed as
    the owner scope, so only chunks owned by that user can be returned.

    Args:
        request: The retrieval request with the query and result count.
        current_user: The authenticated user whose chunks may be returned.
        retriever: The retriever used to find relevant chunks.

    Returns:
        A success envelope with the user's retrieved chunks.

    Raises:
        HTTPException: If the authenticated user has no owner id.
    """
    if not current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authenticated user has no owner id.",
        )
    results = retriever.retrieve(
        request.query,
        k=request.k,
        owner_id=current_user.user_id,
    )
    return SuccessResponse(data=RetrieveResponse(results=results))