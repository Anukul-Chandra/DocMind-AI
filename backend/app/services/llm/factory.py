import logging

from app.config.openrouter_models import OPENROUTER_MODELS
from app.core.config import settings
from app.services.llm.agnes_model_catalog import (
    AgnesModelCatalogError,
    AgnesNoFreeModelsError,
    build_agnes_pool,
)
from app.services.llm.model_catalog import ModelCatalogService, ModelCatalogError
from app.services.llm.model_pool import ModelPoolManager, build_curated_pool
from app.services.llm.opencode_model_pool import build_opencode_pool_manager
from app.services.llm.provider_manager import ProviderManager
from app.services.llm.providers.gemini import GeminiProvider
from app.services.llm.providers.groq import GroqProvider
from app.services.llm.providers.agnes_rotation import AgnesRotatingProvider
from app.services.llm.providers.openrouter import OpenRouterProvider
from app.services.llm.providers.opencode_rotation import OpenCodeRotatingProvider

logger = logging.getLogger(__name__)


def build_openrouter_provider() -> OpenRouterProvider:
    """Build an OpenRouter provider with a dynamically discovered model pool.

    Configuration is read from settings once, here in the composition root,
    and injected into the provider constructor.

    Returns:
        An OpenRouterProvider instance.
    """
    try:
        models = ModelCatalogService(api_key=settings.openrouter_api_key).get_free_models()
    except ModelCatalogError:
        logger.warning("Model discovery failed; using default OpenRouter models")
        models = list(OPENROUTER_MODELS)
    pool_models = build_curated_pool(models, preferred=OPENROUTER_MODELS)
    if not pool_models:
        logger.warning("No suitable OpenRouter models; using trusted defaults")
        pool_models = build_curated_pool(OPENROUTER_MODELS)
    return OpenRouterProvider(
        ModelPoolManager(pool_models),
        api_key=settings.openrouter_api_key,
        timeout=settings.timeout,
    )


def build_opencode_provider() -> OpenCodeRotatingProvider | None:
    """Build an OpenCode rotating provider from the dynamic model catalog.

    Models are discovered live (free catalog -> curation -> dedupe -> stable
    pool); nothing is hardcoded. If discovery fails at construction time,
    ``None`` is returned so the provider chain simply skips OpenCode instead
    of failing startup — mirroring OpenRouter's graceful default-fallback
    path.

    Returns:
        An OpenCodeRotatingProvider, or None when the catalog is unavailable.
    """
    try:
        pool = build_opencode_pool_manager()
    except ModelCatalogError as exc:
        logger.warning(
            "OpenCode model discovery failed; skipping OpenCode provider: %s", exc
        )
        return None
    logger.info("OpenCode pool ready with %d models", pool.total_models())
    return OpenCodeRotatingProvider(pool)


def build_gemini_provider() -> GeminiProvider:
    """Build a Gemini provider with configuration injected from settings.

    Returns:
        A GeminiProvider instance.
    """
    return GeminiProvider(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
    )


def build_groq_provider() -> GroqProvider:
    """Build a Groq provider with configuration injected from settings.

    Returns:
        A GroqProvider instance.
    """
    return GroqProvider(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
    )


def build_agnes_provider() -> AgnesRotatingProvider | None:
    """Build an Agnes AI provider that rotates across the dynamic free pool.

    Free models are discovered from the TTL-cached models.dev pricing source
    (zero input/output cost) rather than hardcoded. If discovery is
    unavailable or yields no free models, the provider still exists but is
    backed solely by the configured ``settings.agnes_model`` fallback — which
    is kept strictly separate from the dynamic free pool and is never claimed
    to be dynamically discovered.

    Returns ``None`` when no API key is configured so the provider is skipped
    gracefully (mirroring OpenCode's discovery-failure skip) instead of
    failing startup. Agnes is opt-in: it is only used when ``agnes`` appears
    in ``settings.provider_priority``.

    Returns:
        An AgnesRotatingProvider instance, or None when the API key is absent.
    """
    if not settings.agnes_api_key:
        return None
    pool: list[str] = []
    try:
        pool = build_agnes_pool()
    except (AgnesModelCatalogError, AgnesNoFreeModelsError) as exc:
        logger.warning(
            "Agnes model discovery unavailable; using configured fallback "
            "only: %s", exc
        )
    return AgnesRotatingProvider(
        api_key=settings.agnes_api_key,
        models=pool,
        fallback_model=settings.agnes_model,
        base_url=settings.agnes_base_url,
        timeout=settings.timeout,
    )


def build_provider_manager() -> ProviderManager:
    """Build a ProviderManager from the configured provider priority.

    Returns:
        A ProviderManager with providers in configured priority order.
    """
    providers: list = []
    for name in settings.provider_priority.split(","):
        name = name.strip()
        if name == "opencode":
            provider = build_opencode_provider()
            if provider is not None:
                providers.append(provider)
        elif name == "openrouter":
            providers.append(build_openrouter_provider())
        elif name == "gemini":
            providers.append(build_gemini_provider())
        elif name == "groq":
            providers.append(build_groq_provider())
        elif name == "agnes":
            provider = build_agnes_provider()
            if provider is not None:
                providers.append(provider)
    return ProviderManager(providers)