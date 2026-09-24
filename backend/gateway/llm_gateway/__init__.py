"""Provider-independent contracts, failover, model pool, and cooldown tracking for the reusable LLM gateway boundary."""

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
from gateway.llm_gateway.provider_manager import (
    ProviderManager,
    _is_image_error,
    _is_image_error_response,
)
from gateway.llm_gateway.model_pool import (
    ModelPoolManager,
    ModelCatalogError,
    NoFreeModelsError,
    curate_models,
    build_curated_pool,
    UNSUITABLE_MODEL_TOKENS,
    _model_slug,
)
from gateway.llm_gateway.cooldown import (
    CooldownTracker,
    DEFAULT_COOLDOWN_SECONDS,
)

__all__ = [
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
    "ProviderManager",
    "_is_image_error",
    "_is_image_error_response",
    "ModelPoolManager",
    "ModelCatalogError",
    "NoFreeModelsError",
    "curate_models",
    "build_curated_pool",
    "UNSUITABLE_MODEL_TOKENS",
    "_model_slug",
    "CooldownTracker",
    "DEFAULT_COOLDOWN_SECONDS",
]