"""Compatibility imports for the legacy DocMind provider contract path."""

from gateway.llm_gateway.contracts import (
    APIError,
    AuthenticationError,
    BaseProvider,
    InvalidResponseError,
    ProviderError,
    RateLimitError,
    RecoverableError,
    build_user_content,
)

__all__ = [
    "APIError",
    "AuthenticationError",
    "BaseProvider",
    "InvalidResponseError",
    "ProviderError",
    "RateLimitError",
    "RecoverableError",
    "build_user_content",
]