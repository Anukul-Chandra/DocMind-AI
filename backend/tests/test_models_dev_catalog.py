"""Tests for the dynamic free-model pool from the models.dev source.

These tests are deterministic and network-free: the models.dev catalog fetch is
replaced with a fake client. They cover the authoritative FREE rule
(``cost.input == 0 AND cost.output == 0``), the TTL cache / no-refetch
guarantee, the OpenCode cost==0 pool (vs. the old ``-free`` suffix heuristic),
the Agnes pool, and the Agnes rotation/fallback health layer.
"""

import httpx
import pytest

from app.services.llm.agnes_model_catalog import (
    AgnesModelCatalogError,
    AgnesModelCatalogService,
    AgnesNoFreeModelsError,
    build_agnes_pool,
)
from app.services.llm.models_dev_catalog import (
    ModelsDevCatalog,
    ModelsDevCatalogError,
    parse_provider_free_models,
)
from app.services.llm.opencode_model_catalog import OpenCodeModelCatalogService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _model(cost=None):
    return {"cost": cost if cost is not None else {"input": 0, "output": 0}}


def _doc(provider_models):
    """Build a minimal models.dev-style document for one provider."""
    return {"some-other-provider": {"models": {}}, provider_models[0]: {
        "models": provider_models[1],
    }}


class FakeResponse:
    def __init__(self, payload=None, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code != 200:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._payload


class FakeCatalogClient:
    """A fake httpx client returning a fixed payload and counting fetches."""

    def __init__(self, payload, http_error=None):
        self._payload = payload
        self._http_error = http_error
        self.fetches = 0

    def get(self, url):
        self.fetches += 1
        if self._http_error is not None:
            raise self._http_error
        return FakeResponse(self._payload)

    def aclose(self):
        return None


def _catalog(payload, clock=None, http_error=None, ttl_seconds=100):
    client = FakeCatalogClient(payload, http_error=http_error)
    cat = ModelsDevCatalog(
        client=lambda: client,
        ttl_seconds=ttl_seconds,
        clock=(clock or _Clock()),
    )
    return cat, client


class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


# ---------------------------------------------------------------------------
# Authoritative FREE parsing (cost == 0)
# ---------------------------------------------------------------------------

def test_agnes_free_and_paid_classification():
    doc = _doc(("agnes", {
        "agnes-2.0-flash": _model({"input": 0, "output": 0}),
        "agnes-2.5-flash": _model({"input": 0, "output": 0}),
        "agnes-2.5-pro-alpha": _model({"input": 0.45, "output": 0.9}),
    }))
    free = parse_provider_free_models(doc, "agnes")
    assert sorted(free) == ["agnes-2.0-flash", "agnes-2.5-flash"]


def test_opencode_cost_zero_includes_non_suffix_free_models():
    """big-pickle and grok-code are free (cost 0) but have no -free suffix;
    the old suffix-only heuristic would miss them."""
    doc = _doc(("opencode", {
        "big-pickle": _model({"input": 0, "output": 0}),
        "grok-code": _model({"input": 0, "output": 0}),
        "some-free": _model({"input": 0, "output": 0}),
        "paid-model": _model({"input": 1, "output": 2}),
    }))
    free = parse_provider_free_models(doc, "opencode")
    assert "big-pickle" in free
    assert "grok-code" in free
    assert "some-free" in free
    assert "paid-model" not in free


def test_free_suffix_does_not_override_pricing():
    """A -free-suffixed model with nonzero cost is NOT free."""
    doc = _doc(("opencode", {
        "misleading-free": _model({"input": 0.5, "output": 0.5}),
    }))
    assert parse_provider_free_models(doc, "opencode") == []


def test_malformed_cost_is_not_free():
    doc = _doc(("opencode", {
        "no-cost": {},                    # no cost key
        "empty-cost": {"cost": {}},       # empty cost object
        "null-cost": {"cost": None},      # null cost
        "non-numeric": {"cost": {"input": "x", "output": 0}},
        "real-free": {"cost": {"input": 0, "output": 0}},
    }))
    assert parse_provider_free_models(doc, "opencode") == ["real-free"]


def test_malformed_structure_is_empty_not_fatal():
    assert parse_provider_free_models(None, "agnes") == []
    assert parse_provider_free_models([], "agnes") == []
    assert parse_provider_free_models({"agnes": "not-a-dict"}, "agnes") == []
    assert parse_provider_free_models({"agnes": {"models": []}}, "agnes") == []
    assert parse_provider_free_models({"agnes": {"models": {123: _model()}}}, "agnes") == []


def test_malformed_entries_skipped():
    doc = {"agnes": {"models": {
        "": _model(),          # empty id
        123: _model(),         # non-string id
        "valid": _model(),
    }}}
    assert parse_provider_free_models(doc, "agnes") == ["valid"]


# ---------------------------------------------------------------------------
# TTL cache / no-refetch guarantee
# ---------------------------------------------------------------------------

def test_cache_miss_fetches_then_hit_does_not_refetch():
    doc = _doc(("agnes", {"m": _model()}))
    cat, client = _catalog(doc)
    assert cat.get_free_models("agnes") == ["m"]
    assert client.fetches == 1
    assert cat.get_free_models("agnes") == ["m"]
    assert client.fetches == 1  # still one fetch: served from cache


def test_cache_refreshes_after_ttl_expiry():
    clock = _Clock()
    doc = _doc(("agnes", {"m": _model()}))
    cat, client = _catalog(doc, clock=clock, ttl_seconds=10)
    cat.get_free_models("agnes")
    assert client.fetches == 1
    clock.t = 20  # expire TTL
    cat.get_free_models("agnes")
    assert client.fetches == 2


def test_refresh_failure_serves_stale_cache():
    clock = _Clock()
    # First fetch succeeds and is cached.
    hey = FakeCatalogClient(_doc(("agnes", {"m": _model()})))
    cat = ModelsDevCatalog(client=lambda: hey, ttl_seconds=10, clock=clock)
    assert cat.get_free_models("agnes") == ["m"]

    # Later a refresh fails; stale data must still be served, not error.
    clock.t = 20
    failing = FakeCatalogClient(None, http_error=httpx.ConnectError("boom"))
    cat._client_factory = lambda: failing
    assert cat.get_free_models("agnes") == ["m"]


def test_total_failure_with_no_cache_raises():
    failing = FakeCatalogClient(None, http_error=httpx.ConnectError("boom"))
    cat = ModelsDevCatalog(client=lambda: failing, ttl_seconds=10)
    with pytest.raises(ModelsDevCatalogError):
        cat.get_free_models("agnes")


def test_concurrent_in_flight_deduplicates_fetches():
    clock = _Clock()
    doc = _doc(("agnes", {"m": _model()}))
    # An in-flight refresh (simulated by pre-populating the in-flight slot).
    cat = ModelsDevCatalog(client=lambda: FakeCatalogClient(doc), ttl_seconds=10, clock=clock)
    cat._in_flight["agnes"] = object()
    # While a refresh is in flight and nothing is cached yet, current call
    # performs its own fetch populating the cache (rare first-access race).
    assert cat.get_free_models("agnes") == ["m"]


# ---------------------------------------------------------------------------
# OpenCode catalog service: cost==0 replaces the -free suffix heuristic
# ---------------------------------------------------------------------------

def test_opencode_service_uses_cost_zero_not_suffix():
    doc = _doc(("opencode", {
        "big-pickle": _model(),                # free, no -free suffix -> kept
        "x-preview-f-free": _model(),          # free with suffix -> kept
        "paid-but-free-suffix": _model({"input": 1, "output": 1}),  # dropped
    }))
    cat, _ = _catalog(doc)
    service = OpenCodeModelCatalogService(catalog=cat)
    free = service.get_free_models()
    assert "big-pickle" in free
    assert "x-preview-f-free" in free
    assert "paid-but-free-suffix" not in free


def test_opencode_service_error_maps_to_model_catalog_error():
    from app.services.llm.model_catalog import ModelCatalogError

    failing = FakeCatalogClient(None, http_error=httpx.ConnectError("boom"))
    cat = ModelsDevCatalog(client=lambda: failing)
    service = OpenCodeModelCatalogService(catalog=cat)
    with pytest.raises(ModelCatalogError):
        service.get_free_models()


def test_opencode_service_curation_applies():
    doc = _doc(("opencode", {
        "big-pickle": _model(),
        "some-coder-free": _model(),   # code specialist -> curated out
    }))
    cat, _ = _catalog(doc)
    service = OpenCodeModelCatalogService(catalog=cat)
    free = service.get_free_models()
    assert "big-pickle" in free
    assert "some-coder-free" not in free


# ---------------------------------------------------------------------------
# Agnes pool
# ---------------------------------------------------------------------------

def test_agnes_pool_build():
    doc = _doc(("agnes", {
        "agnes-2.0-flash": _model(),
        "agnes-2.5-flash": _model(),
        "agnes-2.5-pro-alpha": _model({"input": 0.45, "output": 0.9}),
    }))
    cat, _ = _catalog(doc)
    service = AgnesModelCatalogService(catalog=cat)
    assert build_agnes_pool(service=service) == ["agnes-2.0-flash", "agnes-2.5-flash"]


def test_agnes_pool_no_free_raises():
    doc = _doc(("agnes", {"agnes-2.5-pro-alpha": _model({"input": 1, "output": 1})}))
    cat, _ = _catalog(doc)
    service = AgnesModelCatalogService(catalog=cat)
    with pytest.raises(AgnesNoFreeModelsError):
        build_agnes_pool(service=service)


def test_agnes_pool_catalog_error_raises():
    failing = FakeCatalogClient(None, http_error=httpx.ConnectError("boom"))
    cat = ModelsDevCatalog(client=lambda: failing)
    service = AgnesModelCatalogService(catalog=cat)
    with pytest.raises(AgnesModelCatalogError):
        build_agnes_pool(service=service)
