import logging

from app.services.llm.model_pool import ModelPoolManager, build_curated_pool
from app.services.llm.opencode_model_catalog import (
    OpenCodeModelCatalogService,
)

logger = logging.getLogger(__name__)


def build_opencode_pool(
    service: OpenCodeModelCatalogService | None = None,
    preferred: list[str] | None = None,
) -> list[str]:
    """Build a stable OpenCode model pool from the live catalog.

    The pool is discovered dynamically: current free models are fetched from
    the OpenCode catalog, deduplicated by the catalog layer, filtered through
    the shared general-purpose curation (code/mini/tiny/embedding specialists
    excluded), and returned in deterministic (alphabetical) order. Nothing is
    hardcoded; the pool changes as the dynamic catalog changes.

    Temporary runtime failures (HTTP 400/429/5xx observed against individual
    models) are deliberately NOT encoded as exclusions here — runtime
    availability, cooldown, and dead-model handling belong to a later step.
    No live health checks are performed while building the pool.

    Args:
        service: Optional catalog service override for testing. Defaults to
            a freshly constructed :class:`OpenCodeModelCatalogService`.
        preferred: Optional model ids to place first when present in the
            curated set. OpenCode has no hardcoded trusted defaults.

    Returns:
        The curated, deduplicated pool of free model ids in stable order.

    Raises:
        ModelCatalogError: If the OpenCode catalog request fails.
        NoFreeModelsError: If the catalog exposes no usable free models.
    """
    catalog_service = service or OpenCodeModelCatalogService()
    models = catalog_service.get_free_models()
    return build_curated_pool(models, preferred=preferred)


def build_opencode_pool_manager(
    service: OpenCodeModelCatalogService | None = None,
    preferred: list[str] | None = None,
) -> ModelPoolManager:
    """Build a :class:`ModelPoolManager` over the discovered OpenCode pool.

    Reuses the existing OpenRouter-era pool abstraction so OpenCode can hand
    out one model at a time exactly like OpenRouter does. Rotation/cooldown
    behavior on top of this manager arrives in a later step.

    Args:
        service: Optional catalog service override for testing.
        preferred: Optional model ids to place first when present.

    Returns:
        A ModelPoolManager loaded with the discovered pool.

    Raises:
        ModelCatalogError: If the OpenCode catalog request fails.
        NoFreeModelsError: If the catalog exposes no usable free models.
        ValueError: If the resulting pool is empty.
    """
    pool = build_opencode_pool(service=service, preferred=preferred)
    logger.info("Built OpenCode model pool with %d models", len(pool))
    return ModelPoolManager(pool)
