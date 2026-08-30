"""Agnes AI free-model discovery from the authoritative models.dev source.

Agnes free models are read from ``https://models.dev/api.json`` (the same
authoritative pricing source OpenCode uses) and identified by a zero input and
output cost. Pricing is authoritative: only ``cost.input == 0`` AND
``cost.output == 0`` counts as free, so paid models like
``agnes-2.5-pro-alpha`` are never pooled as free.
"""

from __future__ import annotations

import logging

from app.services.llm.model_catalog import (
    ModelCatalogError,
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

#: models.dev provider key for Agnes.
MODELS_DEV_PROVIDER = "agnes"


class AgnesModelCatalogError(ModelCatalogError):
    """Raised when the Agnes free-model catalog cannot be read."""


class AgnesNoFreeModelsError(NoFreeModelsError):
    """Raised when the Agnes catalog exposes no usable free models."""


class AgnesModelCatalogService:
    """Discover the current free Agnes models from models.dev.

    Reads the process-shared, TTL-cached :class:`ModelsDevCatalog` so the large
    static catalog file is fetched at most once per TTL window, never per
    request. Results are curated (general-purpose only) and returned in
    deterministic order.
    """

    PROVIDER_NAME = "Agnes"

    def __init__(
        self,
        catalog: ModelsDevCatalog | None = None,
        provider: str = MODELS_DEV_PROVIDER,
    ) -> None:
        """Initialize the catalog service.

        Args:
            catalog: Optional :class:`ModelsDevCatalog` override for testing.
                Defaults to the shared process-wide instance.
            provider: The models.dev provider key (``"agnes"``).
        """
        self._catalog = catalog or get_shared_catalog()
        self._provider = provider

    def get_free_models(self) -> list[str]:
        """Return the sorted, curated ids of the current free Agnes models.

        Returns:
            A sorted list of curated free model ids.

        Raises:
            AgnesModelCatalogError: If the models.dev catalog is unavailable
                and no cached data exists.
            AgnesNoFreeModelsError: If no free (or no suitable free) models
                are available.
        """
        try:
            free_models = self._catalog.get_free_models(self._provider)
        except ModelsDevCatalogError as exc:
            logger.warning("Agnes model discovery failed: %s", exc)
            raise AgnesModelCatalogError(
                f"Failed to fetch Agnes models from {MODELS_DEV_URL}: {exc}"
            ) from exc

        free_models = sorted(dict.fromkeys(free_models))

        if not free_models:
            logger.warning("No free %s models available", self.PROVIDER_NAME)
            raise AgnesNoFreeModelsError(
                f"No free {self.PROVIDER_NAME} models available."
            )

        curated = curate_models(free_models)
        if not curated:
            logger.warning(
                "No suitable general-purpose free %s models", self.PROVIDER_NAME
            )
            raise AgnesNoFreeModelsError(
                f"No suitable general-purpose free {self.PROVIDER_NAME} models "
                "available."
            )

        logger.info(
            "Discovered %d curated free %s models", len(curated), self.PROVIDER_NAME
        )
        return curated


def build_agnes_pool(
    service: AgnesModelCatalogService | None = None,
) -> list[str]:
    """Build the sorted, curated Agnes free-model pool from models.dev.

    Args:
        service: Optional catalog service override for testing. Defaults to a
            freshly constructed :class:`AgnesModelCatalogService`.

    Returns:
        The curated pool of free model ids in stable order.

    Raises:
        AgnesModelCatalogError: If the models.dev catalog is unavailable and
            no cached data exists.
        AgnesNoFreeModelsError: If no usable free models are available.
    """
    catalog_service = service or AgnesModelCatalogService()
    return catalog_service.get_free_models()
