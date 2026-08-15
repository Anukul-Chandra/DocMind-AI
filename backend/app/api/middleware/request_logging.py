"""Middleware that records a structured log entry for every HTTP request."""

import time
import uuid
from datetime import datetime, timezone

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.repositories.interfaces import LogRepository
from app.services.logging.request_logger import RequestLogEntry

X_REQUEST_ID = "x-request-id"


class RequestLogMiddleware:
    """ASGI middleware logging one structured entry per HTTP request.

    Each entry records the HTTP method, path, response status code, duration,
    timestamp, a generated request id, and the authenticated user id when a
    protected route resolved one (the auth dependency stamps it into the
    request state). Only metadata is captured - headers, bodies, tokens,
    passwords, and document contents are never logged. CORS preflight (OPTIONS)
    requests are skipped. Logging is best-effort: a repository failure never
    fails or changes the request.

    The generated request id is also attached to the response as the
    ``X-Request-ID`` header so a client-reported request can be correlated with
    its server-side log entry.

    Args:
        app: The inner ASGI application.
        log_repository: The repository persisting the entries.
    """

    def __init__(self, app: ASGIApp, log_repository: LogRepository) -> None:
        self.app = app
        self.log_repository = log_repository

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Apply request logging and pass the request through unchanged.

        Args:
            scope: The ASGI connection scope.
            receive: The ASGI receive callable.
            send: The ASGI send callable.
        """
        if scope["type"] != "http" or scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex
        scope["request_id"] = request_id
        method = scope.get("method", "")
        path = scope.get("path", "")
        started = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code

            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = MutableHeaders(raw=message.get("headers", []))
                headers[X_REQUEST_ID] = request_id
                message["headers"] = headers.raw
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            state = scope.get("state") or {}
            user_id = state.get("user_id", "")
            entry = RequestLogEntry(
                request_id=request_id,
                timestamp=datetime.now(timezone.utc).isoformat(),
                method=method,
                path=path,
                status_code=status_code,
                user_id=str(user_id),
                response_time_ms=elapsed_ms,
                success=100 <= status_code < 400,
            )
            self.log_repository.log(entry)


__all__ = ["RequestLogMiddleware", "X_REQUEST_ID"]