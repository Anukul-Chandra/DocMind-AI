import logging
import re

from openai import OpenAI

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

#: Exact name tokens that mark a model as unsuitable for general
#: conversational/RAG use: code-specialized variants, tiny-capacity tiers,
#: and embedding/reranker specialists.
UNSUITABLE_MODEL_TOKENS: frozenset[str] = frozenset(
    {
        "code",
        "coder",
        "coding",
        "mini",
        "tiny",
        "nano",
        "micro",
        "embed",
        "embedding",
        "rerank",
        "reranker",
    }
)

#: Separators used to split a model name into comparison tokens.
_MODEL_TOKEN_PATTERN = re.compile(r"[^a-zA-Z0-9]+")


def _model_slug(model_id: str) -> str:
    """Return the model-name portion of an id, without provider or suffix.

    Args:
        model_id: An OpenRouter model id (e.g. ``"cohere/north-mini-code:free"``).

    Returns:
        The model name (e.g. ``"north-mini-code"``).
    """
    name = model_id.split("/", 1)[-1]
    return name.split(":", 1)[0]


def curate_models(model_ids: list[str]) -> list[str]:
    """Filter a list of model ids down to general-purpose conversational models.

    Code-specialized, tiny-capacity (mini/tiny/nano/micro), and
    embedding/reranker models are excluded by matching exact tokens from the
    model name. Tokens are compared exactly so names like ``minimax-01`` are
    not misclassified by a ``mini`` substring.

    Args:
        model_ids: OpenRouter model ids to curate.

    Returns:
        A new list containing only the suitable model ids, in input order.
    """
    return [
        model_id
        for model_id in model_ids
        if not (
            UNSUITABLE_MODEL_TOKENS
            & set(_MODEL_TOKEN_PATTERN.split(_model_slug(model_id)))
        )
    ]


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
        """Fetch and return the sorted ids of all general-purpose free models.

        Free models are filtered to those suitable for general
        conversational/RAG use (code/mini/tiny/embedding specialists are
        excluded) before being sorted alphabetically.

        Returns:
            A sorted list of curated free model ids.

        Raises:
            ModelCatalogError: If the OpenRouter request fails.
            NoFreeModelsError: If no free models, or no suitable free models,
                are available.
        """
        free_models = sorted(
            model.id for model in self._fetch_models() if model.id.endswith(":free")
        )

        if not free_models:
            logger.warning("No free OpenRouter models available")
            raise NoFreeModelsError("No free OpenRouter models available.")

        curated = curate_models(free_models)
        if not curated:
            logger.warning("No suitable general-purpose free OpenRouter models")
            raise NoFreeModelsError(
                "No suitable general-purpose free OpenRouter models available."
            )

        logger.info("Discovered %d curated free OpenRouter models", len(curated))
        return curated

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
