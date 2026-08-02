from app.api.routes.chat import router as chat_router
from app.api.routes.documents import router as documents_router

from fastapi import APIRouter

from app.models.responses import HealthData, MessageData, SuccessResponse

router = APIRouter()


@router.get("/", response_model=SuccessResponse[MessageData])
def root() -> SuccessResponse[MessageData]:
    """Return a simple message indicating the API is running.

    Returns:
        A success envelope with a status message.
    """
    return SuccessResponse(data=MessageData(message="DocMind AI API is running"))


@router.get("/health", response_model=SuccessResponse[HealthData])
def health() -> SuccessResponse[HealthData]:
    """Return the service health status.

    Returns:
        A success envelope with the health status.
    """
    return SuccessResponse(data=HealthData(status="healthy"))


__all__ = ["router", "chat_router", "documents_router"]