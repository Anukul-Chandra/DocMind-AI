import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


def build_openrouter_provider():
    from app.config.openrouter_models import OPENROUTER_MODELS
    from app.services.llm.model_catalog import ModelCatalogError, ModelCatalogService
    from app.services.llm.model_pool import ModelPoolManager, build_curated_pool
    from app.services.llm.providers.openrouter import OpenRouterProvider

    try:
        models = ModelCatalogService(api_key=settings.openrouter_api_key).get_free_models()
    except ModelCatalogError:
        models = list(OPENROUTER_MODELS)
    pool_models = build_curated_pool(models, preferred=OPENROUTER_MODELS)
    if not pool_models:
        pool_models = build_curated_pool(OPENROUTER_MODELS)
    return OpenRouterProvider(
        ModelPoolManager(pool_models),
        api_key=settings.openrouter_api_key,
        timeout=settings.timeout,
    )


def build_opencode_provider():
    from app.services.llm.model_catalog import ModelCatalogError
    from app.services.llm.opencode_model_pool import build_opencode_pool_manager
    from app.services.llm.providers.opencode_rotation import OpenCodeRotatingProvider

    try:
        pool = build_opencode_pool_manager()
    except ModelCatalogError as exc:
        logger.warning(
            "OpenCode model discovery failed; skipping OpenCode provider: %s", exc
        )
        return None
    return OpenCodeRotatingProvider(pool)


def build_gemini_provider():
    from app.services.llm.providers.gemini import GeminiProvider

    return GeminiProvider(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
    )


def build_groq_provider():
    from app.services.llm.providers.groq import GroqProvider

    return GroqProvider(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
    )


def build_agnes_provider():
    if not settings.agnes_api_key:
        return None

    from app.services.llm.agnes_model_catalog import (
        AgnesModelCatalogError,
        AgnesNoFreeModelsError,
        build_agnes_pool,
    )
    from app.services.llm.providers.agnes_rotation import AgnesRotatingProvider

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


def build_provider_manager():
    from app.services.llm.provider_manager import ProviderManager

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
