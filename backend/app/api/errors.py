import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.models.responses import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)

_STATUS_CODES: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "bad_request",
    status.HTTP_401_UNAUTHORIZED: "unauthorized",
    status.HTTP_403_FORBIDDEN: "forbidden",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
    status.HTTP_409_CONFLICT: "conflict",
    status.HTTP_422_UNPROCESSABLE_CONTENT: "validation_error",
    status.HTTP_429_TOO_MANY_REQUESTS: "too_many_requests",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "internal_server_error",
    status.HTTP_502_BAD_GATEWAY: "bad_gateway",
}


def _error_code(status_code: int) -> str:
    """Return the stable error code for an HTTP status code.

    Args:
        status_code: The HTTP status code.

    Returns:
        A machine-readable error code.
    """
    return _STATUS_CODES.get(status_code, f"http_{status_code}")


async def _http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Render an HTTPException using the standard error envelope.

    Handles both FastAPI HTTPExceptions and Starlette-level HTTP errors such
    as route-not-found responses, so every error follows the same envelope.

    Args:
        request: The incoming request.
        exc: The exception being handled.

    Returns:
        A JSONResponse with the error envelope.
    """
    detail: Any = exc.detail
    message = detail if isinstance(detail, str) else str(detail)
    payload = ErrorResponse(
        error=ErrorDetail(
            code=_error_code(exc.status_code),
            message=message,
        )
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=payload.model_dump(),
    )


async def _validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Render request validation failures using the standard error envelope.

    Args:
        request: The incoming request.
        exc: The validation error being handled.

    Returns:
        A JSONResponse with the error envelope.
    """
    payload = ErrorResponse(
        error=ErrorDetail(
            code="validation_error",
            message="Request validation failed.",
        )
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=payload.model_dump(),
    )


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Render unexpected exceptions as a standardized 500 response.

    The original exception is logged so failures remain diagnosable while the
    client only sees the generic envelope.

    Args:
        request: The incoming request.
        exc: The unhandled exception.

    Returns:
        A JSONResponse with the error envelope.
    """
    logger.error("Unhandled exception: %s", exc, exc_info=exc)
    payload = ErrorResponse(
        error=ErrorDetail(
            code="internal_server_error",
            message="An unexpected error occurred.",
        )
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=payload.model_dump(),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register the standardized error handlers on the application.

    Args:
        app: The FastAPI application to configure.
    """
    app.add_exception_handler(HTTPException, _http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(
        RequestValidationError, _validation_exception_handler
    )
    app.add_exception_handler(Exception, _unhandled_exception_handler)
