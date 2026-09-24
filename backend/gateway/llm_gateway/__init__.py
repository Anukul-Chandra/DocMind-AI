"""Provider-independent contracts, failover, model pool, and cooldown tracking for the reusable LLM gateway boundary.

Public API keeps only the reusable surface; internal ``_`` helpers remain
importable via their submodules but are no longer advertised in ``__all__``.
"""

from gateway.llm_gateway.catalog import (
    ModelsDevCatalog,
    ModelsDevCatalogError,
    get_shared_catalog,
    parse_provider_free_models,
)
from gateway.llm_gateway.contracts import (
    APIError,
    AuthenticationError,
    BaseProvider,
    InvalidResponseError,
    LLMUnavailableError,
    LLMResponse,
    LLMStreamChunk,
    ProviderError,
    RateLimitError,
    RecoverableError,
    build_user_content,
)
from gateway.llm_gateway.cooldown import CooldownTracker
from gateway.llm_gateway.failure_policy import classify_failure
from gateway.llm_gateway.model_pool import (
    ModelCatalogError,
    ModelPoolManager,
    NoFreeModelsError,
    build_curated_pool,
    curate_models,
)
from gateway.llm_gateway.provider_manager import ProviderManager

__all__ = [
    # contracts — ProviderError hierarchy + base + responses
    "APIError",
    "AuthenticationError",
    "BaseProvider",
    "InvalidResponseError",
    "LLMUnavailableError",
    "LLMResponse",
    "LLMStreamChunk",
    "ProviderError",
    "RateLimitError",
    "RecoverableError",
    "build_user_content",
    # catalog errors (part of ProviderError hierarchy)
    "ModelCatalogError",
    "NoFreeModelsError",
    "ModelsDevCatalogError",
    # core gateway components
    "ProviderManager",
    "ModelPoolManager",
    "curate_models",
    "build_curated_pool",
    "CooldownTracker",
    "classify_failure",
    "ModelsDevCatalog",
    "parse_provider_free_models",
    "get_shared_catalog",
]