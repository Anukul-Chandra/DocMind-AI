import logging

from app.services.llm.model_catalog import ModelCatalogService

logger = logging.getLogger(__name__)

OPENCODE_CATALOG_BASE_URL = "https://opencode.ai/zen/v1"

#: OpenCode marks explicitly free models with a ``-free`` id suffix. Pricing
#: metadata in the catalog is currently ``null`` for every entry, so pricing
#: cannot be used to detect free models.
OPENCODE_FREE_MODEL_SUFFIX = "-free"

#: Placeholder credential for the OpenAI-compatible SDK client. The OpenCode
#: model catalog endpoint is public, but the SDK refuses to construct a client
#: without a non-empty api key.
_OPENCODE_PLACEHOLDER_API_KEY = "opencode"

#: Timeout (seconds) for the catalog discovery request. Discovery runs during
#: provider construction, so it must fail fast rather than stall startup.
DEFAULT_CATALOG_TIMEOUT_SECONDS = 10.0


def is_free_opencode_model(model_id: str) -> bool:
    """Return True when an OpenCode model id is explicitly marked free.

    Args:
        model_id: An OpenCode model id (e.g. ``"mimo-v2.5-free"``).

    Returns:
        True if the id ends with the OpenCode free-model suffix.
    """
    return isinstance(model_id, str) and model_id.endswith(OPENCODE_FREE_MODEL_SUFFIX)


class OpenCodeModelCatalogService(ModelCatalogService):
    """Discover available free models from the OpenCode /models endpoint.

    Reuses the shared catalog machinery (fetching, safe parsing, curation,
    error types) from :class:`ModelCatalogService`, retargeted at the OpenCode
    Zen catalog. The catalog is dynamic: free models can appear or disappear
    at any time, so nothing here is hardcoded and temporary runtime
    unavailability is deliberately not encoded as permanent exclusion
    (runtime rotation/cooldown handling arrives in a later step).
    """

    PROVIDER_NAME = "OpenCode"
    FREE_MODEL_SUFFIX = OPENCODE_FREE_MODEL_SUFFIX

    def __init__(
        self,
        api_key: str = "",
        base_url: str = OPENCODE_CATALOG_BASE_URL,
        timeout: float = DEFAULT_CATALOG_TIMEOUT_SECONDS,
    ) -> None:
        """Initialize the catalog for the OpenCode Zen endpoint.

        Args:
            api_key: Optional OpenCode API key. The public catalog endpoint
                works without one; a placeholder is used when empty because
                the underlying SDK requires a non-empty key.
            base_url: The OpenAI-compatible OpenCode base URL.
            timeout: HTTP timeout in seconds for the catalog request.
        """
        super().__init__(
            api_key=api_key.strip() or _OPENCODE_PLACEHOLDER_API_KEY,
            base_url=base_url,
            timeout=timeout,
        )

    def _extract_ids(self, models: list[object]) -> list[str]:
        """Extract valid model ids, collapsing duplicate catalog entries.

        The dynamic OpenCode catalog can repeat ids across pages/refreshes;
        duplicates are removed while preserving first-seen order so pool
        ordering stays deterministic.

        Args:
            models: Raw model objects from the OpenCode catalog.

        Returns:
            A deduplicated list of valid model ids in catalog order.
        """
        return list(dict.fromkeys(super()._extract_ids(models)))
