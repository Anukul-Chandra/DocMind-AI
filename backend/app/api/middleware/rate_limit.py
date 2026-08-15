"""Lightweight in-memory rate limiting for the API.

A fixed-window counter is kept per client key (the client IP, or the leftmost
``X-Forwarded-For`` value when proxy trust is enabled). Requests under the
``/auth`` prefix are counted against a stricter limit; everything else uses the
general limit. The limiter is process-local and single-thread-safe; it is
deliberately not a distributed solution (no Redis or other external service),
which matches the current single-process JSON-backed deployment.

Blocked requests return the application's standard error envelope with the
``too_many_requests`` code so clients see the same shape as every other error.
"""

import logging
import threading
import time

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.models.responses import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)

TOO_MANY_REQUESTS_STATUS = 429
TOO_MANY_REQUESTS_MESSAGE = "Too many requests. Please try again later."
DEFAULT_WINDOW_SECONDS = 60
_MAX_BUCKETS = 100_000


class FixedWindowLimiter:
    """In-memory fixed-window rate limiter keyed by client identifier.

    Each key has an independent window of ``window_seconds`` during which at
    most ``limit`` requests are allowed. State is process-local and resets on
    restart.

    Attributes:
        limit: The maximum number of requests allowed per window.
        window_seconds: The length of the window in seconds.
    """

    def __init__(self, limit: int, window_seconds: int = DEFAULT_WINDOW_SECONDS):
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if window_seconds < 1:
            raise ValueError("window_seconds must be >= 1")
        self.limit = limit
        self.window_seconds = window_seconds
        self._buckets: dict[str, list[float | int]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        """Record one request for ``key`` and report whether it is permitted.

        Args:
            key: The client identifier (for example an IP address).

        Returns:
            True if the request is within the window limit, False otherwise.
        """
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                self._buckets[key] = [now, 1]
                if len(self._buckets) > _MAX_BUCKETS:
                    self._prune(now)
                return True
            window_start, count = bucket
            if now - window_start >= self.window_seconds:
                bucket[0], bucket[1] = now, 1
                return True
            bucket[1] = count + 1
            return bucket[1] <= self.limit

    def _prune(self, now: float) -> None:
        """Drop buckets whose window has fully elapsed to bound memory.

        Args:
            now: The current monotonic time.
        """
        stale = [
            key
            for key, (window_start, _) in self._buckets.items()
            if now - window_start >= self.window_seconds
        ]
        for key in stale:
            del self._buckets[key]


class RateLimitMiddleware:
    """ASGI middleware enforcing per-client rate limits.

    Requests whose path falls under any ``auth_paths`` prefix are counted
    against ``auth_limiter`` (a stricter limit), everything else against
    ``general_limiter``. CORS preflight (OPTIONS) requests pass through without
    being counted so origin discovery is never throttled.

    Args:
        app: The inner ASGI application.
        general_limiter: The limiter for non-auth endpoints.
        auth_limiter: The limiter for auth endpoints. None applies the general
            limit everywhere.
        auth_paths: Path prefixes treated as sensitive (for example
            ``("/auth",)``).
        trust_proxy_headers: When True, prefer the leftmost X-Forwarded-For
            value as the client identifier.
    """

    def __init__(
        self,
        app: ASGIApp,
        general_limiter: FixedWindowLimiter,
        auth_limiter: FixedWindowLimiter | None = None,
        auth_paths: tuple[str, ...] = ("/auth",),
        trust_proxy_headers: bool = False,
    ):
        self.app = app
        self.general_limiter = general_limiter
        self.auth_limiter = auth_limiter
        self.auth_paths = tuple(
            path.rstrip("/") for path in auth_paths if path.strip()
        )
        self.trust_proxy_headers = trust_proxy_headers

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Apply the rate limit and pass the request on.

        Args:
            scope: The ASGI connection scope.
            receive: The ASGI receive callable.
            send: The ASGI send callable.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return

        limiter = self._limiter_for(scope.get("path", ""))
        key = self._client_key(scope)
        if limiter is not None and not limiter.allow(key):
            logger.warning(
                "Rate limit exceeded for client %s on %s %s",
                key,
                scope.get("method"),
                scope.get("path"),
            )
            response = JSONResponse(
                status_code=TOO_MANY_REQUESTS_STATUS,
                content=ErrorResponse(
                    error=ErrorDetail(
                        code="too_many_requests",
                        message=TOO_MANY_REQUESTS_MESSAGE,
                    )
                ).model_dump(),
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)

    def _limiter_for(self, path: str) -> FixedWindowLimiter | None:
        """Select the limiter for a request path.

        Args:
            path: The request path.

        Returns:
            The auth limiter for sensitive paths, otherwise the general one.
        """
        if self.auth_limiter is None:
            return self.general_limiter
        normalized = path.rstrip("/")
        for prefix in self.auth_paths:
            if normalized == prefix or normalized.startswith(f"{prefix}/"):
                return self.auth_limiter
        return self.general_limiter

    def _client_key(self, scope: Scope) -> str:
        """Resolve the client identifier for rate limiting.

        Args:
            scope: The ASGI connection scope.

        Returns:
            The leftmost X-Forwarded-For value when proxy trust is enabled and
            present, otherwise the direct peer address.
        """
        if self.trust_proxy_headers:
            for name, value in scope.get("headers", ()):
                if name.lower() == b"x-forwarded-for":
                    forwarded = value.split(b",", 1)[0].strip().decode("ascii", "ignore")
                    if forwarded:
                        return forwarded
        client = scope.get("client")
        return client[0] if client else "unknown"


__all__ = ["FixedWindowLimiter", "RateLimitMiddleware"]