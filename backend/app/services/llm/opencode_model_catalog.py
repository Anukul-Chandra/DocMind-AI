import logging

from app.services.llm.model_catalog import (
    ModelCatalogError,
    ModelCatalogService,
    NoFreeModelsError,
    curate_models,
)
from app.services.llm.models_dev_catalog import (
    MODELS_DEV_URL,
    ModelsDevCatalog,
    ModelsDevCatalogError,
    get_shared_catalog,
)

logger = logging.getLogger(__name__)

OPENCODE_CATALOG_BASE_URL = "https://opencode.ai/zen/v1"

#: OpenCode historically marked explicitly free models with a ``-free`` id
#: suffix. Pricing is now the authoritative signal (see the module docstring
#: for :mod:`app.services.llm.models_dev_catalog`), so this suffix is kept only
#: as a compatibility helper and is no longer the discovery mechanism.
OPENCODE_FREE_MODEL_SUFFIX = "-free"

#: models.dev provider key for OpenCode (matches the ``opencode`` top-level
#: object in https://models.dev/api.json).
MODELS_DEV_PROVIDER = "opencode"

#: Placeholder credential for the OpenAI-compatible SDK client. The OpenCode
#: model catalog endpoint is public, but the SDK refuses to construct a client
#: without a non-empty api key.
_OPENCODE_PLACEHOLDER_API_KEY = "opencode"

#: Timeout (seconds) for the catalog discovery request. Discovery runs during
#: provider construction, so it must fail fast rather than stall startup.
DEFAULT_CATALOG_TIMEOUT_SECONDS = 10.0


def is_free_opencode_model(model_id: str) -> bool:
    """Return True when an OpenCode model id is explicitly marked free.

    Note: this id-suffix check is retained for compatibility. The authoritative
    free-model discovery now uses the models.dev pricing (cost == 0).

    Args:
        model_id: An OpenCode model id (e.g. ``"mimo-v2.5-free"``).

    Returns:
        True if the id ends with the OpenCode free-model suffix.
    """
    return isinstance(model_id, str) and model_id.endswith(OPENCODE_FREE_MODEL_SUFFIX)


class OpenCodeModelCatalogService(ModelCatalogService):
    """Discover available free models from the authoritative models.dev source.

    Free models are read from ``https://models.dev/api.json`` (the same
    authoritative pricing source OpenCode itself uses) and identified by a zero
    input and output cost. The models.dev document is cached in-process with a
    TTL, so discovery does not re-fetch per request. The result is then filtered
    through the shared general-purpose curation and returned in deterministic
    order.

    The catalog is dynamic: free models can appear or disappear at any time, so
    nothing here is hardcoded and temporary runtime unavailability is
    deliberately not encoded as permanent exclusion (runtime rotation/cooldown
    handling lives in the rotating provider layer).
    """

    PROVIDER_NAME = "OpenCode"
    FREE_MODEL_SUFFIX = OPENCODE_FREE_MODEL_SUFFIX

    def __init__(
        self,
        api_key: str = "",
        base_url: str = MODELS_DEV_URL,
        timeout: float = DEFAULT_CATALOG_TIMEOUT_SECONDS,
        catalog: ModelsDevCatalog | None = None,
        provider: str = MODELS_DEV_PROVIDER,
    ) -> None:
        """Initialize the catalog for the OpenCode models.dev source.

        Args:
            api_key: Ignored for models.dev (public). Kept for API compat with
                the shared :class:`ModelCatalogService` constructor.
            base_url: Unused by the models.dev-backed lookup; kept for
                compatibility.
            timeout: HTTP timeout in seconds for the catalog request.
            catalog: Optional :class:`ModelsDevCatalog` override for testing.
                Defaults to the shared process-wide instance.
            provider: The models.dev provider key to read (``"opencode"``).
        """
        super().__init__(
            api_key=api_key.strip() or _OPENCODE_PLACEHOLDER_API_KEY,
            base_url=base_url,
            timeout=timeout,
        )
        self._catalog = catalog or get_shared_catalog()
        self._provider = provider

    def get_free_models(self) -> list[str]:
        """Fetch and return the sorted ids of curated free OpenCode models.

        Free models are read from the models.dev pricing catalog (zero input
        and output cost) and filtered to those suitable for general
        conversational/RAG use before being sorted alphabetically.

        Returns:
            A sorted list of curated free model ids.

        Raises:
            ModelCatalogError: If the models.dev catalog is unavailable and no
                cached data exists.
            NoFreeModelsError: If no free models, or no suitable free models,
                are available.
        """
        try:
            free_models = self._catalog.get_free_models(self._provider)
        except ModelsDevCatalogError as exc:
            logger.warning("OpenCode model discovery failed: %s", exc)
            raise ModelCatalogError(
                f"Failed to fetch OpenCode models from {MODELS_DEV_URL}: {exc}"
            ) from exc

        free_models = sorted(dict.fromkeys(free_models))

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

    def _extract_ids(self, models: list[object]) -> list[str]:
        """Extract valid model ids, collapsing duplicate catalog entries.

        Retained from the parent for compatibility; the models.dev-backed
        :meth:`get_free_models` is the actual discovery path.

        Args:
            models: Raw model objects.

        Returns:
            A deduplicated list of valid model ids in order.
        """
        return list(dict.fromkeys(super()._extract_ids(models)))
