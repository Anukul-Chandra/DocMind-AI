"""Deterministic unit tests for the OpenCode model catalog discovery layer.

Verifies, without any network or live OpenCode calls:

- The OpenCode Zen /models endpoint is queried through an OpenAI-compatible
  client with the correct base URL and a short discovery timeout.
- Only explicitly free models (``-free`` id suffix) are selected; paid and
  unmarked models are excluded.
- Missing ``pricing`` metadata (null for every current entry) does not break
  discovery.
- Malformed, empty, and unexpected catalog payloads are handled safely.
- HTTP/API failures surface as :class:`ModelCatalogError` instead of crashing.
- Duplicate model ids are deduplicated safely.

Usage (from backend/):
    ../.venv/bin/python app/scripts/test_opencode_model_catalog.py
"""

from types import SimpleNamespace
from unittest.mock import patch

from app.services.llm.model_catalog import (
    ModelCatalogError,
    ModelCatalogService,
    NoFreeModelsError,
)
from app.services.llm.opencode_model_catalog import (
    DEFAULT_CATALOG_TIMEOUT_SECONDS,
    OPENCODE_CATALOG_BASE_URL,
    OPENCODE_FREE_MODEL_SUFFIX,
    OpenCodeModelCatalogService,
    is_free_opencode_model,
)

# Real-world-shaped fixtures: pricing is null and paid models carry no marker.
PAID_IDS = [
    "claude-opus-5",
    "gpt-5.4",
    "grok-4.6",
]
FREE_IDS = [
    "hy3-free",
    "mimo-v2.5-free",
    "nemotron-3-ultra-free",
]


def _catalog_entry(model_id, **extra):
    """Build a raw OpenAI-compatible catalog model object."""
    fields = {
        "id": model_id,
        "object": "model",
        "created": 1787667810,
        "owned_by": "opencode",
        "pricing": None,
    }
    fields.update(extra)
    return SimpleNamespace(**fields)


def _catalog_response(entries):
    """Build a stand-in for the OpenAI SDK's paginated models response."""
    return SimpleNamespace(data=list(entries))


class FakeModelsClient:
    """Fake OpenAI client whose ``models.list`` replays canned data/errors."""

    def __init__(self, data=None, error=None):
        self._data = data if data is not None else []
        self._error = error
        self.calls = 0

    @property
    def models(self):
        return self

    def list(self):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return _catalog_response(self._data)


def _service_with(client: FakeModelsClient) -> OpenCodeModelCatalogService:
    """Build an OpenCode catalog service wired to a fake SDK client."""
    service = OpenCodeModelCatalogService()
    service._client = client
    return service


def test_catalog_returns_models() -> bool:
    """A healthy catalog returns every valid model id and the free subset."""
    entries = [_catalog_entry(model_id) for model_id in PAID_IDS + FREE_IDS]
    service = _service_with(FakeModelsClient(data=entries))

    all_models = service.get_all_models()
    if all_models != PAID_IDS + FREE_IDS:
        print(f"FAIL: unexpected all-models result: {all_models}")
        return False

    free_models = service.get_free_models()
    expected = sorted(FREE_IDS)
    if free_models != expected:
        print(f"FAIL: expected free models {expected}, got {free_models}")
        return False

    total, free_count = service.count_models()
    if (total, free_count) != (len(PAID_IDS) + len(FREE_IDS), len(FREE_IDS)):
        print(f"FAIL: unexpected counts: {(total, free_count)}")
        return False

    if service._client.calls == 0:
        print("FAIL: catalog endpoint was never queried")
        return False
    return True


def test_only_explicitly_free_selected() -> bool:
    """Only ids ending in '-free' are treated as free."""
    mixed = [
        "mimo-v2.5-free",
        "free-tier-preview",
        "freewill",
        "hy3-free",
        "laguna-s-2.1-FREE",
        "nemotron-3.5-lightning-free",
    ]
    service = _service_with(FakeModelsClient(data=[_catalog_entry(m) for m in mixed]))

    free_models = service.get_free_models()

    # 'free-tier-preview' and 'freewill' do not end with '-free'; suffix
    # matching is case-sensitive like the catalog convention.
    expected = ["hy3-free", "mimo-v2.5-free", "nemotron-3.5-lightning-free"]
    if free_models != expected:
        print(f"FAIL: expected only explicit -free ids {expected}, got {free_models}")
        return False

    for model_id in mixed:
        wanted = model_id.endswith(OPENCODE_FREE_MODEL_SUFFIX)
        if is_free_opencode_model(model_id) != wanted:
            print(f"FAIL: is_free_opencode_model misjudged {model_id!r}")
            return False
    return True


def test_non_free_excluded() -> bool:
    """Paid/unmarked OpenCode models never enter the free pool."""
    paid_only = [
        "claude-opus-5",
        "deepseek-v4-flash",
        "gpt-5.6-sol",
        "kimi-k3",
    ]
    service = _service_with(
        FakeModelsClient(data=[_catalog_entry(m) for m in paid_only])
    )

    try:
        service.get_free_models()
    except NoFreeModelsError:
        return True
    print(f"FAIL: expected NoFreeModelsError for paid-only catalog, got {service.get_all_models()}")
    return False


def test_missing_pricing_does_not_break_discovery() -> bool:
    """Null or absent pricing metadata is irrelevant to discovery."""
    entries = [
        _catalog_entry("hy3-free", pricing=None),
        _catalog_entry("mimo-v2.5-free"),  # pricing key entirely absent
        _catalog_entry("claude-opus-5", pricing=None),
        _catalog_entry("x-preview-f-free", pricing={"prompt": None}),
    ]
    service = _service_with(FakeModelsClient(data=entries))

    free_models = service.get_free_models()

    expected = ["hy3-free", "mimo-v2.5-free", "x-preview-f-free"]
    if free_models != expected:
        print(f"FAIL: missing pricing broke discovery: {free_models}")
        return False
    return True


def test_malformed_entries_skipped() -> bool:
    """Malformed/unexpected catalog objects are skipped, not fatal."""
    entries = [
        _catalog_entry(None),  # null id
        _catalog_entry(""),  # empty id
        _catalog_entry(12345),  # non-string id
        SimpleNamespace(object="model"),  # missing id entirely
        "not-a-model-object",  # junk payload entry
        _catalog_entry("hy3-free"),
    ]
    service = _service_with(FakeModelsClient(data=entries))

    free_models = service.get_free_models()

    if free_models != ["hy3-free"]:
        print(f"FAIL: malformed entries broke discovery: {free_models}")
        return False
    return True


def test_empty_response_raises_no_free_models() -> bool:
    """An empty catalog maps to the existing safe failure representation."""
    service = _service_with(FakeModelsClient(data=[]))

    try:
        service.get_free_models()
    except NoFreeModelsError as exc:
        if not isinstance(exc, ModelCatalogError):
            print("FAIL: NoFreeModelsError must subclass ModelCatalogError")
            return False
        return True
    print("FAIL: empty catalog did not raise NoFreeModelsError")
    return False


def test_http_failure_handled_safely() -> bool:
    """Transport/API failures raise ModelCatalogError instead of crashing."""
    failures = [
        ConnectionError("connection refused"),
        TimeoutError("catalog request timed out"),
        RuntimeError("unexpected SDK failure"),
    ]
    for error in failures:
        service = _service_with(FakeModelsClient(error=error))
        try:
            service.get_free_models()
        except ModelCatalogError:
            continue
        print(f"FAIL: {type(error).__name__} escaped as a crash")
        return False
    return True


def test_duplicate_ids_deduplicated() -> bool:
    """Duplicate catalog entries collapse to a single pool member."""
    entries = [
        _catalog_entry("hy3-free"),
        _catalog_entry("hy3-free"),
        _catalog_entry("mimo-v2.5-free"),
        _catalog_entry("mimo-v2.5-free", owned_by="other"),
    ]
    service = _service_with(FakeModelsClient(data=entries))

    free_models = service.get_free_models()

    if free_models != ["hy3-free", "mimo-v2.5-free"]:
        print(f"FAIL: duplicates not handled safely: {free_models}")
        return False

    _, free_count = service.count_models()
    if free_count != 2:
        print(f"FAIL: duplicate free count mismatch: {free_count}")
        return False
    return True


def test_curation_still_applies() -> bool:
    """The shared general-purpose curation filters the OpenCode free pool."""
    entries = [
        _catalog_entry("hy3-free"),
        _catalog_entry("some-coder-free"),
        _catalog_entry("tiny-preview-free"),
        _catalog_entry("text-embedding-free"),
    ]
    service = _service_with(FakeModelsClient(data=entries))

    free_models = service.get_free_models()

    if free_models != ["hy3-free"]:
        print(f"FAIL: specialist free models were not curated out: {free_models}")
        return False
    return True


def test_client_configuration() -> bool:
    """The SDK client targets the OpenCode base URL with a short timeout."""
    captured: dict = {}

    def _record_openai_client(*args, **kwargs):
        captured.clear()
        captured.update(kwargs)
        return FakeModelsClient()

    with patch(
        "app.services.llm.model_catalog.OpenAI", side_effect=_record_openai_client
    ):
        if not issubclass(OpenCodeModelCatalogService, ModelCatalogService):
            print("FAIL: OpenCode catalog is not a ModelCatalogService")
            return False

        service = OpenCodeModelCatalogService(timeout=3.5)

    if captured.get("base_url") != OPENCODE_CATALOG_BASE_URL:
        print(f"FAIL: wrong catalog base URL: {captured.get('base_url')}")
        return False
    if captured.get("timeout") != 3.5:
        print(f"FAIL: custom timeout not forwarded: {captured.get('timeout')}")
        return False
    # The public catalog needs no credential; empty keys use the placeholder
    # because the underlying SDK rejects empty strings outright.
    if captured.get("api_key") != "opencode":
        print(f"FAIL: blank api key not replaced: {captured.get('api_key')!r}")
        return False

    with patch(
        "app.services.llm.model_catalog.OpenAI", side_effect=_record_openai_client
    ):
        OpenCodeModelCatalogService(api_key="  secret-key  ")
    if captured.get("api_key") != "secret-key":
        print(f"FAIL: supplied api key not trimmed: {captured.get('api_key')!r}")
        return False

    if not 0 < DEFAULT_CATALOG_TIMEOUT_SECONDS <= 30:
        print(f"FAIL: discovery timeout not short-bounded: "
              f"{DEFAULT_CATALOG_TIMEOUT_SECONDS}")
        return False

    if ModelCatalogService.PROVIDER_NAME != "OpenRouter":
        print("FAIL: parent provider name changed")
        return False
    if ModelCatalogService.FREE_MODEL_SUFFIX != ":free":
        print("FAIL: parent free suffix changed")
        return False
    if OpenCodeModelCatalogService.FREE_MODEL_SUFFIX != OPENCODE_FREE_MODEL_SUFFIX:
        print("FAIL: OpenCode free suffix misconfigured")
        return False
    return True


async def main() -> None:
    """Run all OpenCode catalog scenarios and report the overall result."""
    print("=" * 60)
    print("OpenCode Model Catalog Test")
    print("=" * 60)

    scenarios = [
        ("Catalog: healthy catalog returns models", test_catalog_returns_models),
        ("Free detection: only explicit -free selected", test_only_explicitly_free_selected),
        ("Free detection: non-free excluded", test_non_free_excluded),
        ("Robustness: missing pricing tolerated", test_missing_pricing_does_not_break_discovery),
        ("Robustness: malformed entries skipped", test_malformed_entries_skipped),
        ("Robustness: empty catalog -> NoFreeModelsError", test_empty_response_raises_no_free_models),
        ("Robustness: HTTP/API failure -> ModelCatalogError", test_http_failure_handled_safely),
        ("Robustness: duplicate ids deduplicated", test_duplicate_ids_deduplicated),
        ("Reuse: shared curation still applies", test_curation_still_applies),
        ("Wiring: base URL, timeout, key, inheritance", test_client_configuration),
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
    print(f"OpenCode Catalog Test {'PASSED' if passed else 'FAILED'}")
    print("=" * 60)
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
