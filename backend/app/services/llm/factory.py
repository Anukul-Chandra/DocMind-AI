from app.core.config import settings
from app.services.llm.provider_manager import ProviderManager
from app.services.llm.providers.base import BaseProvider
from app.services.llm.providers.cerebras import CerebrasProvider
from app.services.llm.providers.gemini import GeminiProvider
from app.services.llm.providers.github_models import GitHubModelsProvider
from app.services.llm.providers.groq import GroqProvider
from app.services.llm.providers.openrouter import OpenRouterProvider
from app.services.llm.providers.sambanova import SambaNovaProvider

PROVIDERS: dict[str, type[BaseProvider]] = {
    "openrouter": OpenRouterProvider,
    "github": GitHubModelsProvider,
    "cerebras": CerebrasProvider,
    "gemini": GeminiProvider,
    "groq": GroqProvider,
    "sambanova": SambaNovaProvider,
}


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
        providers.append(PROVIDERS[name]())
    return ProviderManager(providers)
