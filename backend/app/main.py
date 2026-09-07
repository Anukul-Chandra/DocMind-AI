import time as _time
import sys as _sys

def _t(label: str) -> None:
    print(f"[{_time.strftime('%X')}] (diag-main) {label}", flush=True)

_t("app.main import started")

_t("importing fastapi")
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
_t("fastapi imported")

_t("importing app.api.dependencies (heavy — triggers transitive chain)")
from app.api.dependencies import get_log_repository
_t("app.api.dependencies imported")

_t("importing app.api.errors")
from app.api.errors import register_exception_handlers
_t("app.api.errors imported")

_t("importing app.api.middleware.rate_limit")
from app.api.middleware.rate_limit import FixedWindowLimiter, RateLimitMiddleware
_t("rate_limit imported")

_t("importing app.api.middleware.request_logging")
from app.api.middleware.request_logging import RequestLogMiddleware
_t("request_logging imported")

_t("importing app.api.routes.auth")
from app.api.routes.auth import router as auth_router
_t("routes.auth imported")

_t("importing app.api.routes.chat")
from app.api.routes.chat import router as chat_router
_t("routes.chat imported")

_t("importing app.api.routes.conversations")
from app.api.routes.conversations import router as conversations_router
_t("routes.conversations imported")

_t("importing app.api.routes.documents")
from app.api.routes.documents import router as documents_router
_t("routes.documents imported")

_t("importing app.api.routes (root)")
from app.api.routes import router
_t("app.api.routes imported")

_t("importing app.api.retrieve")
from app.api.retrieve import router as retrieve_router
_t("app.api.retrieve imported")

_t("importing app.core.config")
from app.core.config import settings
_t("config imported (Settings() resolved)")

_t("ALL imports done — constructing FastAPI app")

_docs_enabled = settings.enable_docs
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=settings.app_description,
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)
_t("FastAPI app constructed")

register_exception_handlers(app)
_t("exception handlers registered")


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
    _t("security middleware added")

_add_request_logging_middleware()
_t("request logging middleware added")

app.include_router(router)
app.include_router(retrieve_router)
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(conversations_router)
app.include_router(documents_router)
_t("all routers included")

_t("app.main import finished — FastAPI app ready")
