"""Gateway provider adapters (OpenAI-compatible).

Single-model providers that are fully gateway-owned and have no DocMind
dependencies. They are available as ``gateway.llm_gateway.providers.AgnesProvider``
and ``gateway.llm_gateway.providers.OpenCodeProvider`` without importing ``app``.
Implementation is not changed by this re-export.
"""

from gateway.llm_gateway.providers.agnes import (
    AGNES_ATTEMPT_TIMEOUT_SECONDS,
    AGNES_DEFAULT_BASE_URL,
    AgnesProvider,
)
from gateway.llm_gateway.providers.opencode import (
    OPENCODE_BASE_URL,
    OpenCodeProvider,
)

__all__ = [
    "AgnesProvider",
    "AGNES_DEFAULT_BASE_URL",
    "AGNES_ATTEMPT_TIMEOUT_SECONDS",
    "OpenCodeProvider",
    "OPENCODE_BASE_URL",
]
