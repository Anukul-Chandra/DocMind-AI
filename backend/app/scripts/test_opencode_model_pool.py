"""Deterministic unit tests for the OpenCode model pool construction.

Verifies, without any network or live OpenCode calls:

- a current catalog produces a stable pool
- only explicitly free models enter the pool; paid/unmarked models and
  specialist models are excluded via the shared curation
- duplicate ids collapse to a single pool member
- dynamic catalog changes are reflected in the rebuilt pool
- previously observed temporary runtime failures (400/429/5xx probes) are
  NOT encoded as permanent exclusions anywhere
- the existing OpenRouter pool behavior is unchanged
- empty catalogs and catalog failures surface via the existing error types

Usage (from backend/):
    PYTHONPATH=. ../.venv/bin/python app/scripts/test_opencode_model_pool.py
"""

from unittest.mock import patch

from app.services.llm.model_pool import build_curated_pool
from app.services.llm.opencode_model_catalog import (
    OpenCodeModelCatalogService,
)
from app.services.llm.opencode_model_pool import (
    build_opencode_pool,
    build_opencode_pool_manager,
)

# Models observed failing at runtime during manual probing. These were
# transient endpoint states, not permanent exclusions.
PREVIOUSLY_PROBED_MODELS = [
    "deepseek-v4-flash-free",          # was 400 Model unavailable
    "x-preview-f-free",                # was 503 Endpoint unavailable
    "muse-spark-1.2-contributor-free", # was 503 Endpoint unavailable
    "mimo-v2.5-free",                  # was 429 FreeUsageLimitError
    "hy3-free",                        # was 200
    "nemotron-3-ultra-free",           # was 502 upstream overloaded
    "nemotron-3.5-lightning-free",     # was 200
    "laguna-s-2.1-free",               # was 503 Endpoint unavailable
]


class FakeCatalogService:
    """Duck-typed stand-in mirroring the real catalog service contract.

    ``get_free_models`` returns sorted, deduplicated, explicitly-free ids,
    exactly like :meth:`OpenCodeModelCatalogService.get_free_models`.
    """

    def __init__(self, raw_catalog=None, error=None):
        self._raw_catalog = list(raw_catalog) if raw_catalog else []
        self._error = error
        self.calls = 0

    def get_free_models(self):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return sorted({
            model_id
            for model_id in set(self._raw_catalog)
            if isinstance(model_id, str) and model_id.endswith("-free")
        })


def test_catalog_produces_pool() -> bool:
    """A healthy catalog yields a non-empty, deterministic pool."""
    service = FakeCatalogService(raw_catalog=PREVIOUSLY_PROBED_MODELS)

    pool = build_opencode_pool(service=service)
    again = build_opencode_pool(service=FakeCatalogService(
        raw_catalog=PREVIOUSLY_PROBED_MODELS
    ))

    if service.calls != 1:
        print(f"FAIL: expected exactly one catalog query, got {service.calls}")
        return False
    if not pool:
        print("FAIL: healthy catalog produced an empty pool")
        return False
    if pool != sorted(pool):
        print(f"FAIL: pool ordering not deterministic: {pool}")
        return False
    if pool != again:
        print(f"FAIL: same catalog produced different pools: {pool} vs {again}")
        return False
    return True


def test_only_free_models_enter() -> bool:
    """Paid/unmarked models never enter the pool."""
    service = FakeCatalogService(raw_catalog=[
        "claude-opus-5",
        "gpt-5.6-sol",
        "kimi-k3",
        "hy3-free",
        "mimo-v2.5-free",
    ])

    pool = build_opencode_pool(service=service)

    if pool != ["hy3-free", "mimo-v2.5-free"]:
        print(f"FAIL: unexpected pool: {pool}")
        return False
    return True


def test_specialist_free_models_curated_out() -> bool:
    """The shared curation excludes code/mini/tiny/embedding specialists."""
    service = FakeCatalogService(raw_catalog=[
        "some-coder-free",
        "gpt-nano-free",
        "text-embedding-free",
        "tiny-experiment-free",
        "hy3-free",
        "nemotron-3.5-lightning-free",
    ])

    pool = build_opencode_pool(service=service)

    if pool != ["hy3-free", "nemotron-3.5-lightning-free"]:
        print(f"FAIL: specialists leaked into pool: {pool}")
        return False
    return True


def test_duplicates_removed() -> bool:
    """Duplicate free ids collapse to a single pool member."""
    service = FakeCatalogService(
        raw_catalog=["hy3-free", "hy3-free", "mimo-v2.5-free"]
    )

    pool = build_opencode_pool(service=service)
    manager = build_opencode_pool_manager(service=FakeCatalogService(
        raw_catalog=["hy3-free", "hy3-free", "mimo-v2.5-free"]
    ))

    if pool != ["hy3-free", "mimo-v2.5-free"]:
        print(f"FAIL: duplicates survived: {pool}")
        return False
    if manager.total_models() != 2:
        print(f"FAIL: manager loaded duplicates: {manager.total_models()}")
        return False
    return True


def test_dynamic_catalog_changes_reflected() -> bool:
    """A changed catalog produces a correspondingly changed pool."""
    day_one = FakeCatalogService(raw_catalog=["hy3-free", "mimo-v2.5-free"])
    pool_one = build_opencode_pool(service=day_one)

    day_two = FakeCatalogService(
        raw_catalog=["laguna-s-2.1-free", "hy3-free"]  # mimo gone, laguna new
    )
    pool_two = build_opencode_pool(service=day_two)

    if pool_one != ["hy3-free", "mimo-v2.5-free"]:
        print(f"FAIL: unexpected day-one pool: {pool_one}")
        return False
    if pool_two != ["hy3-free", "laguna-s-2.1-free"]:
        print(f"FAIL: dynamic change not reflected: {pool_two}")
        return False
    return True


def test_runtime_failures_not_excluded() -> bool:
    """Models that failed temporary runtime probes stay in the pool."""
    service = FakeCatalogService(raw_catalog=sorted(PREVIOUSLY_PROBED_MODELS))

    pool = build_opencode_pool(service=service)

    missing = [model for model in PREVIOUSLY_PROBED_MODELS if model not in pool]
    if missing:
        print(f"FAIL: temporarily-failing models wrongly excluded: {missing}")
        return False
    # The manager hands out one model at a time from the same full pool.
    manager = build_opencode_pool_manager(
        service=FakeCatalogService(raw_catalog=sorted(PREVIOUSLY_PROBED_MODELS))
    )
    first = manager.get_current_model()
    nxt = manager.move_next()
    if first == nxt or nxt not in pool:
        print(f"FAIL: manager cannot serve models one at a time: {first}, {nxt}")
        return False
    return True


def test_no_hardcoded_model_lists() -> bool:
    """The pool module must not embed a fixed model list or exclusion list."""
    import inspect

    from app.services.llm import opencode_model_pool

    source = inspect.getsource(opencode_model_pool)
    for marker in PREVIOUSLY_PROBED_MODELS:
        if marker in source:
            print(f"FAIL: hardcoded model id found in pool module: {marker}")
            return False
    return True


def test_openrouter_pool_behavior_unchanged() -> bool:
    """The shared pool builder keeps its OpenRouter-era semantics."""
    candidates = [
        "cohere/north-mini-code:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "minimax/minimax-01:free",
        "qwen/qwen3-coder:free",
        "openai/gpt-4o-mini:free",
    ]
    preferred = ["meta-llama/llama-3.3-70b-instruct:free"]

    pool = build_curated_pool(candidates, preferred=preferred)

    if pool != [
        "meta-llama/llama-3.3-70b-instruct:free",
        "minimax/minimax-01:free",
    ]:
        print(f"FAIL: OpenRouter curated pool changed: {pool}")
        return False

    no_preferred = build_curated_pool(candidates)
    if no_preferred != [
        "meta-llama/llama-3.3-70b-instruct:free",
        "minimax/minimax-01:free",
    ]:
        print(f"FAIL: OpenRouter default pool changed: {no_preferred}")
        return False
    return True


def test_default_service_wiring() -> bool:
    """Without an override, the real OpenCode catalog service is used."""
    created = {}

    class RecordingService(OpenCodeModelCatalogService):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            created["instance"] = self

    def fake_get_free_models(inner_self):
        return ["hy3-free", "mimo-v2.5-free"]

    with patch(
        "app.services.llm.opencode_model_pool.OpenCodeModelCatalogService",
        RecordingService,
    ), patch.object(
        OpenCodeModelCatalogService, "get_free_models", fake_get_free_models
    ):
        pool = build_opencode_pool()

    if pool != ["hy3-free", "mimo-v2.5-free"]:
        print(f"FAIL: default wiring produced wrong pool: {pool}")
        return False
    if "instance" not in created:
        print("FAIL: real catalog service was not constructed by default")
        return False
    return True


def test_empty_catalog_handled_safely() -> bool:
    """An empty free catalog surfaces the existing NoFreeModelsError."""
    from app.services.llm.model_catalog import NoFreeModelsError

    service = FakeCatalogService(raw_catalog=[], error=NoFreeModelsError("none"))

    try:
        build_opencode_pool(service=service)
    except NoFreeModelsError:
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: expected NoFreeModelsError, got {type(exc).__name__}: {exc}")
        return False
    print("FAIL: empty catalog did not raise")
    return False


def test_catalog_failure_uses_existing_conventions() -> bool:
    """Transport failures surface as ModelCatalogError, untouched."""
    from app.services.llm.model_catalog import ModelCatalogError

    service = FakeCatalogService(error=ModelCatalogError("catalog down"))

    try:
        build_opencode_pool(service=service)
        build_opencode_pool_manager(service=service)
    except ModelCatalogError:
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: expected ModelCatalogError, got {type(exc).__name__}: {exc}")
        return False
    print("FAIL: catalog failure did not raise")
    return False


def main() -> None:
    """Run all OpenCode pool scenarios and report the overall result."""
    print("=" * 60)
    print("OpenCode Model Pool Test")
    print("=" * 60)

    scenarios = [
        ("Pool: healthy catalog produces deterministic pool", test_catalog_produces_pool),
        ("Pool: only free models enter", test_only_free_models_enter),
        ("Curation: specialist free models excluded", test_specialist_free_models_curated_out),
        ("Pool: duplicates removed", test_duplicates_removed),
        ("Dynamic: catalog changes reflected", test_dynamic_catalog_changes_reflected),
        ("Runtime: probe failures NOT excluded", test_runtime_failures_not_excluded),
        ("Policy: no hardcoded model lists", test_no_hardcoded_model_lists),
        ("Reuse: OpenRouter pool behavior unchanged", test_openrouter_pool_behavior_unchanged),
        ("Wiring: real catalog service used by default", test_default_service_wiring),
        ("Robustness: empty catalog safe", test_empty_catalog_handled_safely),
        ("Robustness: catalog failure conventions", test_catalog_failure_uses_existing_conventions),
    ]

    passed = True
    for label, scenario in scenarios:
        print()
        print(label)
        try:
            result = scenario()
        except Exception as exc:  # noqa: BLE001 - report any crash as failure
            print(f"CRASHED: {type(exc).__name__}: {exc}")
            result = False
        print("PASSED" if result else "FAILED")
        passed = passed and result

    print()
    print("=" * 60)
    print(f"OpenCode Pool Test {'PASSED' if passed else 'FAILED'}")
    print("=" * 60)
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
