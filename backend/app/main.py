from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.dependencies import get_log_repository
from app.api.errors import register_exception_handlers
from app.api.middleware.rate_limit import FixedWindowLimiter, RateLimitMiddleware
from app.api.middleware.request_logging import RequestLogMiddleware
from app.api.routes import auth_router, chat_router, documents_router, router
from app.api.retrieve import router as retrieve_router
from app.core.config import settings

_docs_enabled = settings.enable_docs
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=settings.app_description,
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)

register_exception_handlers(app)


def _add_security_middleware() -> None:
    """Add CORS and rate-limiting middleware to the application.

    CORS is added last so it wraps the rate limiter: preflight OPTIONS
    requests are answered by the CORS middleware without ever being counted,
    while actual requests that pass CORS still hit the rate limiter.
    """
    app.add_middleware(
        RateLimitMiddleware,
        general_limiter=FixedWindowLimiter(settings.rate_limit_per_minute),
        auth_limiter=FixedWindowLimiter(settings.rate_limit_auth_per_minute),
        auth_paths=("/auth",),
        trust_proxy_headers=settings.rate_limit_trust_proxy_headers,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )


def _add_request_logging_middleware() -> None:
    """Add request logging outermost so every response (including rate-limit
    and CORS rejections) is recorded with its status code and duration."""
    app.add_middleware(
        RequestLogMiddleware,
        log_repository=get_log_repository(),
    )


if settings.rate_limit_enabled or settings.cors_origins.strip():
    _add_security_middleware()

_add_request_logging_middleware()

app.include_router(router)
app.include_router(retrieve_router)
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(documents_router)
