import logging

from app.config.openrouter_models import OPENROUTER_MODELS
from app.core.config import settings
from app.services.llm.model_catalog import ModelCatalogService, ModelCatalogError
from app.services.llm.model_pool import ModelPoolManager, build_curated_pool
from app.services.llm.provider_manager import ProviderManager
from app.services.llm.providers.gemini import GeminiProvider
from app.services.llm.providers.groq import GroqProvider
from app.services.llm.providers.openrouter import OpenRouterProvider

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


def build_provider_manager() -> ProviderManager:
    """Build a ProviderManager from the configured provider priority.

    Returns:
        A ProviderManager with providers in configured priority order.
    """
    providers: list = []
    for name in settings.provider_priority.split(","):
        name = name.strip()
        if name == "openrouter":
            providers.append(build_openrouter_provider())
        elif name == "gemini":
            providers.append(build_gemini_provider())
        elif name == "groq":
            providers.append(build_groq_provider())
    return ProviderManager(providers)