import logging

from openai import OpenAI

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class ModelCatalogError(Exception):
    """Raised when fetching models from OpenRouter fails."""


class NoFreeModelsError(ModelCatalogError):
    """Raised when OpenRouter returns no free models."""


class ModelCatalogService:
    """Discover available free models from the OpenRouter /models endpoint."""

    def __init__(
        self,
        api_key: str,
        base_url: str = OPENROUTER_BASE_URL,
    ) -> None:
        """Initialize the catalog with an OpenRouter API key.

        Args:
            api_key: The OpenRouter API key used to list models.
            base_url: The OpenRouter base URL.
        """
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    def get_all_models(self) -> list[str]:
        """Return the complete list of model ids from OpenRouter.

        Returns:
            A list of all model ids before any filtering.
        """
        return [model.id for model in self._fetch_models()]

    def get_free_models(self) -> list[str]:
        """Fetch and return the sorted ids of all free OpenRouter models.

        Returns:
            A sorted list of free model ids.

        Raises:
            ModelCatalogError: If the OpenRouter request fails.
            NoFreeModelsError: If no free models are available.
        """
        free_models = sorted(
            model.id for model in self._fetch_models() if model.id.endswith(":free")
        )

        if not free_models:
            logger.warning("No free OpenRouter models available")
            raise NoFreeModelsError("No free OpenRouter models available.")

        logger.info("Discovered %d free OpenRouter models", len(free_models))
        return free_models

    def count_models(self) -> tuple[int, int]:
        """Return the total model count and the free model count.

        Returns:
            A tuple of (total models, free models).
        """
        models = self._fetch_models()
        total = len(models)
        free = sum(1 for model in models if model.id.endswith(":free"))
        return total, free

    def _fetch_models(self) -> list[object]:
        """Fetch the raw model list from the OpenRouter /models endpoint.

        Returns:
            The raw list of model objects.

        Raises:
            ModelCatalogError: If the OpenRouter request fails.
        """
        try:
            response = self._client.models.list()
        except Exception as exc:
            logger.exception("Failed to fetch models from OpenRouter")
            raise ModelCatalogError(f"Failed to fetch models from OpenRouter: {exc}") from exc
        return response.data
