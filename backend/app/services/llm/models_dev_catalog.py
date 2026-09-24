"""Compatibility adapter for the extracted gateway catalog.

The reusable catalog discovery (TTL cache, stale-while-revalidate, pricing-based
free-model parsing) now lives in ``gateway.llm_gateway.catalog``. This module
preserves the existing DocMind import path
``app.services.llm.models_dev_catalog`` so production configuration, factory,
and tests continue to work without changes.
"""

from gateway.llm_gateway.catalog import (
    DEFAULT_CACHE_TTL_SECONDS,
    DEFAULT_CATALOG_TIMEOUT_SECONDS,
    MODELS_DEV_URL,
    ModelsDevCatalog,
    ModelsDevCatalogError,
    _CatalogEntry,
    _is_free_cost,
    get_shared_catalog,
    parse_provider_free_models,
)

__all__ = [
    "MODELS_DEV_URL",
    "DEFAULT_CACHE_TTL_SECONDS",
    "DEFAULT_CATALOG_TIMEOUT_SECONDS",
    "ModelsDevCatalogError",
    "_CatalogEntry",
    "_is_free_cost",
    "parse_provider_free_models",
    "ModelsDevCatalog",
    "get_shared_catalog",
]
