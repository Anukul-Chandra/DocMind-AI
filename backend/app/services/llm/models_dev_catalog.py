"""Authoritative free-model source backed by https://models.dev/api.json.

This is the exact machine-readable pricing catalog that OpenCode itself uses
(see opencode issue #2901). A model is FREE only when BOTH its input and
output prices are zero (``cost.input == 0 AND cost.output == 0``). Pricing is
the authoritative signal; id-suffix heuristics (e.g. OpenCode's ``-free``) are
replaced by this cost check because some genuinely free models (``big-pickle``,
``grok-code``) carry no free suffix, and some paid models are unrelated to
their name.

The catalog is a single large static file (~4.4 MB). It is fetched lazily on
first access and cached in-process with a TTL so it is never re-fetched per
request. A stale-but-valid cached payload is served while a refresh runs so a
slow catalog never blocks a request.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MODELS_DEV_URL = "https://models.dev/api.json"

#: How long a fetched catalog is considered fresh before the next access
#: triggers a lazy refresh. Long enough to avoid refetching per request, short
#: enough that newly added/removed free models propagate within a day.
DEFAULT_CACHE_TTL_SECONDS = 6 * 60 * 60

#: Timeout bound for a single catalog fetch. The catalog is only fetched on a
#: cache miss, never on the request hot path, but we still bound it so a slow
#: network cannot stall a request indefinitely.
DEFAULT_CATALOG_TIMEOUT_SECONDS = 10.0


class ModelsDevCatalogError(Exception):
    """Raised when the models.dev catalog cannot be fetched or parsed."""


class _CatalogEntry:
    """Minimal parsed representation of one provider's free-model list."""

    __slots__ = ("models", "fetched_at")

    def __init__(self, models: list[str], fetched_at: float) -> None:
        self.models = models
        self.fetched_at = fetched_at


def _is_free_cost(cost: Any) -> bool:
    """Return True when a raw ``cost`` object means the model is free.

    A model is free only when both input and output are zero. Malformed cost
    objects (missing/None/non-numeric fields) are treated as *not* free so
    paid or unknown-priced models are never accidentally pooled.
    """
    if not isinstance(cost, dict):
        return False
    inp = cost.get("input")
    out = cost.get("output")
    try:
        return float(inp) == 0.0 and float(out) == 0.0
    except (TypeError, ValueError):
        return False


def parse_provider_free_models(data: Any, provider: str) -> list[str]:
    """Extract the free model ids for ``provider`` from a models.dev payload.

    ``data`` is the parsed top-level JSON from models.dev. Provider models are
    read from ``data[provider]["models"]`` (a dict of id -> metadata). Only
    models whose cost is exactly zero are returned, in catalog order.
    Malformed structure or malformed entries degrade to an empty list rather
    than raising.

    Args:
        data: The parsed models.dev JSON document.
        provider: The provider key (e.g. ``"agnes"`` or ``"opencode"``).

    Returns:
        The list of free model ids in catalog order (may be empty).
    """
    if not isinstance(data, dict):
        return []
    provider_block = data.get(provider)
    if not isinstance(provider_block, dict):
        return []
    models = provider_block.get("models")
    if not isinstance(models, dict):
        return []

    free_ids: list[str] = []
    for model_id, meta in models.items():
        if not isinstance(model_id, str) or not model_id.strip():
            continue
        if not isinstance(meta, dict):
            continue
        if _is_free_cost(meta.get("cost")):
            free_ids.append(model_id)
    return free_ids


class ModelsDevCatalog:
    """Process-local, TTL-cached reader over the models.dev catalog.

    Thread-safe: concurrent accessors share one in-flight refresh and serve
    stale-but-valid data rather than blocking on a slow network fetch.
    """

    def __init__(
        self,
        client: Callable[[], httpx.AsyncClient] | None = None,
        ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
        url: str = MODELS_DEV_URL,
        timeout: float = DEFAULT_CATALOG_TIMEOUT_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Initialize the TTL cache.

        Args:
            client: Factory returning an httpx client used to fetch the
                catalog. Defaults to a plain :class:`httpx.AsyncClient`.
            ttl_seconds: Freshness window before the next access refreshes.
            url: Catalog URL to fetch.
            timeout: HTTP timeout for the catalog fetch.
            clock: Injectable monotonic-style clock (test seam).
        """
        self._client_factory = client or (lambda: httpx.AsyncClient(timeout=timeout))
        self._ttl_seconds = max(0.0, ttl_seconds)
        self._url = url
        self._timeout = timeout
        self._clock = clock

        self._lock = threading.Lock()
        self._cache: dict[str, _CatalogEntry] = {}
        self._in_flight: dict[str, object] = {}

    def _fetch(self) -> dict:
        """Fetch and parse the models.dev document."""
        client = self._client_factory()
        try:
            response = client.get(self._url)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ModelsDevCatalogError(
                f"Failed to fetch models.dev catalog: {exc}"
            ) from exc
        finally:
            client.aclose()

    def get_free_models(self, provider: str) -> list[str]:
        """Return the authoritative free models for a provider.

        Serves from the TTL cache when fresh. On a miss, refreshes lazily (one
        network fetch, which concurrent callers deduplicate against). A stale
        cache is served while a refresh runs so the hot path never blocks.
        On refresh failure the last good cached list is kept; if nothing is
        cached the error is raised so callers can fall back.

        Args:
            provider: The models.dev provider key.

        Returns:
            The ordered list of free model ids.

        Raises:
            ModelsDevCatalogError: If there is no usable cache and the fetch
                fails or yields an unparseable document.
        """
        with self._lock:
            cached = self._cache.get(provider)
            now = self._clock()
            if cached is not None and now - cached.fetched_at < self._ttl_seconds:
                return list(cached.models)
            if self._in_flight.get(provider) is not None:
                # A refresh is already underway; serve stale data instead of
                # issuing a duplicate HTTP call.
                if cached is not None:
                    return list(cached.models)
            self._in_flight[provider] = object()

        try:
            data = self._fetch()
            free_ids = parse_provider_free_models(data, provider)
            with self._lock:
                self._cache[provider] = _CatalogEntry(free_ids, self._clock())
            return list(free_ids)
        except ModelsDevCatalogError:
            with self._lock:
                cached = self._cache.get(provider)
            if cached is not None:
                logger.warning(
                    "models.dev refresh failed for %r; serving stale cache "
                    "(%d models)", provider, len(cached.models)
                )
                return list(cached.models)
            raise
        finally:
            with self._lock:
                self._in_flight.pop(provider, None)


_shared_catalog: ModelsDevCatalog | None = None


def get_shared_catalog() -> ModelsDevCatalog:
    """Return the process-wide shared models.dev catalog (single TTL cache).

    Both the Agnes and OpenCode model pools read from this one instance so
    the large catalog file is fetched at most once per TTL window across the
    whole process rather than once per catalog service constructed.
    """
    global _shared_catalog
    if _shared_catalog is None:
        _shared_catalog = ModelsDevCatalog()
    return _shared_catalog
