import logging

from app.config.openrouter_models import OPENROUTER_MODELS
from app.core.config import settings
from app.services.llm.model_catalog import ModelCatalogService, ModelCatalogError
from app.services.llm.model_pool import ModelPoolManager
from app.services.llm.provider_manager import ProviderManager
from app.services.llm.providers.base import BaseProvider
from app.services.llm.providers.cerebras import CerebrasProvider
from app.services.llm.providers.gemini import GeminiProvider
from app.services.llm.providers.github_models import GitHubModelsProvider
from app.services.llm.providers.groq import GroqProvider
from app.services.llm.providers.openrouter import OpenRouterProvider
from app.services.llm.providers.sambanova import SambaNovaProvider

logger = logging.getLogger(__name__)

PROVIDERS: dict[str, type[BaseProvider]] = {
    "openrouter": OpenRouterProvider,
    "github": GitHubModelsProvider,
    "cerebras": CerebrasProvider,
    "gemini": GeminiProvider,
    "groq": GroqProvider,
    "sambanova": SambaNovaProvider,
}


def build_openrouter_provider() -> OpenRouterProvider:
    """Build an OpenRouter provider with a dynamically discovered model pool.

    Returns:
        An OpenRouterProvider instance.
    """
    try:
        models = ModelCatalogService().get_free_models()
    except ModelCatalogError:
        logger.warning("Model discovery failed; using default OpenRouter models")
        models = list(OPENROUTER_MODELS)
    return OpenRouterProvider(ModelPoolManager(models))


def build_provider_manager() -> ProviderManager:
    """Build a ProviderManager from the configured provider priority.

    Returns:
        A ProviderManager with providers in configured priority order.
    """
    providers: list[BaseProvider] = []
    for name in settings.provider_priority.split(","):
        name = name.strip()
        if not name or name not in PROVIDERS:
            continue
        if name == "openrouter":
            providers.append(build_openrouter_provider())
        else:
            providers.append(PROVIDERS[name]())
    return ProviderManager(providers)
