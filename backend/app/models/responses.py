from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class SuccessResponse(BaseModel, Generic[T]):
    """Standard envelope for all successful API responses.

    Attributes:
        success: Always True for successful responses.
        data: The typed payload returned by the endpoint.
    """

    success: bool = True
    data: T


class ErrorDetail(BaseModel):
    """Structured error payload exposed to API clients.

    Attributes:
        code: A stable, machine-readable error code.
        message: A human-readable description of the failure.
    """

    code: str
    message: str


class ErrorResponse(BaseModel):
    """Standard envelope for all API error responses.

    Attributes:
        success: Always False for error responses.
        error: The structured error payload.
    """

    success: bool = False
    error: ErrorDetail


class MessageData(BaseModel):
    """Typed payload for a simple status message."""

    message: str


class HealthData(BaseModel):
    """Typed payload for the health check endpoint."""

    status: str


class UploadResult(BaseModel):
    """Typed payload returned after a successful document upload."""

    document_id: str
    workspace_id: str
    filename: str
    chunks: int
    embeddings: int
    status: str


class DeleteResult(BaseModel):
    """Typed payload returned after a successful document or conversation deletion."""

    document_id: str | None = None
    conversation_id: str | None = None
    status: str
