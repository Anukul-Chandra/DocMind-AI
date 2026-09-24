"""Compatibility shim for the extracted gateway Agnes provider."""

import httpx as _httpx

# Expose ``httpx`` so legacy test monkeypatches of
# ``app.services.llm.providers.agnes.httpx.AsyncClient`` continue to work.
# The gateway provider and this shim share the same ``httpx`` module object,
# so patching ``AsyncClient`` here affects the gateway implementation as well.
httpx = _httpx

from gateway.llm_gateway.providers.agnes import (
    AGNES_ATTEMPT_TIMEOUT_SECONDS,
    AGNES_DEFAULT_BASE_URL,
    AgnesProvider,
    request_completion,
)

__all__ = [
    "AGNES_ATTEMPT_TIMEOUT_SECONDS",
    "AGNES_DEFAULT_BASE_URL",
    "AgnesProvider",
    "request_completion",
]
