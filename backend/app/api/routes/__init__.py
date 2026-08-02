from app.api.routes.chat import router as chat_router
from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def root() -> dict[str, str]:
    """Return a simple message indicating the API is running.

    Returns:
        A dict with a status message.
    """
    return {"message": "DocMind AI API is running"}


@router.get("/health")
def health() -> dict[str, str]:
    """Return the service health status.

    Returns:
        A dict with a health status.
    """
    return {"status": "healthy"}


__all__ = ["router", "chat_router"]