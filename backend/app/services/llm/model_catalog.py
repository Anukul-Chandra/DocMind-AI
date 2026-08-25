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
    """Discover available free models from an OpenAI-compatible /models endpoint.

    The default configuration targets OpenRouter. Subclasses can point the
    service at another provider by overriding :attr:`PROVIDER_NAME` and
    :attr:`FREE_MODEL_SUFFIX` and supplying a different ``base_url``.
    """

    #: Human-readable provider name used in logs and error messages.
    PROVIDER_NAME: str = "OpenRouter"

    #: Model id suffix that marks a model as explicitly free in this catalog.
    FREE_MODEL_SUFFIX: str = ":free"

    def __init__(
        self,
        api_key: str,
        base_url: str = OPENROUTER_BASE_URL,
        timeout: float | None = None,
    ) -> None:
        """Initialize the catalog with a provider API key.

        Args:
            api_key: The API key used to list models.
            base_url: The OpenAI-compatible catalog base URL.
            timeout: Optional HTTP timeout in seconds for catalog requests.
                ``None`` keeps the underlying client's default timeout.
        """
        client_kwargs: dict = {}
        if timeout is not None:
            client_kwargs["timeout"] = timeout
        self._client = OpenAI(api_key=api_key, base_url=base_url, **client_kwargs)

    def get_all_models(self) -> list[str]:
        """Return the complete list of model ids from the provider.

        Returns:
            A list of all valid model ids before any filtering. Malformed
            entries without a usable id are skipped.
        """
        return self._extract_ids(self._fetch_models())

    def get_free_models(self) -> list[str]:
        """Fetch and return the sorted ids of all general-purpose free models.

        Free models are identified by the provider's free-model id suffix and
        filtered to those suitable for general conversational/RAG use
        (code/mini/tiny/embedding specialists are excluded) before being
        sorted alphabetically.

        Returns:
            A sorted list of curated free model ids.

        Raises:
            ModelCatalogError: If the request to the provider fails.
            NoFreeModelsError: If no free models, or no suitable free models,
                are available.
        """
        free_models = sorted(
            model_id
            for model_id in self._extract_ids(self._fetch_models())
            if model_id.endswith(self.FREE_MODEL_SUFFIX)
        )

        if not free_models:
            logger.warning("No free %s models available", self.PROVIDER_NAME)
            raise NoFreeModelsError(f"No free {self.PROVIDER_NAME} models available.")

        curated = curate_models(free_models)
        if not curated:
            logger.warning(
                "No suitable general-purpose free %s models", self.PROVIDER_NAME
            )
            raise NoFreeModelsError(
                f"No suitable general-purpose free {self.PROVIDER_NAME} models "
                "available."
            )

        logger.info(
            "Discovered %d curated free %s models", len(curated), self.PROVIDER_NAME
        )
        return curated

    def count_models(self) -> tuple[int, int]:
        """Return the total model count and the free model count.

        Returns:
            A tuple of (total models, free models).
        """
        models = self._fetch_models()
        total = len(models)
        free = sum(
            1
            for model_id in self._extract_ids(models)
            if model_id.endswith(self.FREE_MODEL_SUFFIX)
        )
        return total, free

    def _extract_ids(self, models: list[object]) -> list[str]:
        """Extract valid string model ids from raw catalog objects.

        Malformed or unexpected entries (missing, empty, or non-string ids)
        are skipped instead of breaking discovery.

        Args:
            models: Raw model objects from the provider catalog.

        Returns:
            A list of valid model ids in catalog order.
        """
        model_ids: list[str] = []
        for model in models:
            model_id = getattr(model, "id", None)
            if isinstance(model_id, str) and model_id.strip():
                model_ids.append(model_id)
        return model_ids

    def _fetch_models(self) -> list[object]:
        """Fetch the raw model list from the provider /models endpoint.

        Returns:
            The raw list of model objects.

        Raises:
            ModelCatalogError: If the request to the provider fails.
        """
        try:
            response = self._client.models.list()
        except Exception as exc:
            logger.exception("Failed to fetch models from %s", self.PROVIDER_NAME)
            raise ModelCatalogError(
                f"Failed to fetch models from {self.PROVIDER_NAME}: {exc}"
            ) from exc
        return response.data
