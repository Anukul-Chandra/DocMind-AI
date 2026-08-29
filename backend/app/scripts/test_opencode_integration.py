"""Deterministic integration tests for OpenCode's active provider-chain slot.

Verifies, without any network or live LLM calls:

- OpenCode is built first in the provider priority chain from the dynamic
  catalog (no hardcoded model ids)
- OpenCode rotates internally across its pool (429/503/timeout, dead-model
  skipping) BEFORE any provider-level failover
- only a fully exhausted OpenCode pool hands off to OpenRouter, and only an
  exhausted OpenRouter hands off to Gemini
- the ProviderManager response contract (LLMResponse: provider/model/text)
  is unchanged

Usage (from backend/):
    PYTHONPATH=. ../.venv/bin/python app/scripts/test_opencode_integration.py
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch

from app.core.config import settings
from app.models.llm import LLMResponse
from app.services.llm.factory import build_opencode_provider, build_provider_manager
from app.services.llm.model_pool import ModelPoolManager
from app.services.llm.provider_manager import ProviderManager
from app.services.llm.providers.base import BaseProvider
from app.services.llm.providers.openrouter import OpenRouterProvider
from app.services.llm.providers.opencode_rotation import (
    OpenCodeRotatingProvider,
)

OC_MODELS = ["oc-a-free", "oc-b-free", "oc-c-free"]

CATALOG_IDS = [
    # paid / unmarked entries must never reach the OpenCode pool
    "claude-opus-5",
    "gpt-5.4",
    # free entries; one duplicate to prove dedupe in the live pipeline
    "oc-b-free",
    "oc-a-free",
    "oc-a-free",
    "oc-c-free",
]


def completion(text: str) -> tuple[int, dict]:
    """Return a valid 200 chat completion response."""
    return 200, {"choices": [{"message": {"role": "assistant", "content": text}}]}


class ScriptedResponse:
    """Minimal stand-in for httpx.Response."""

    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload) if payload is not None else ""

    def json(self) -> dict:
        return self._payload


class ScriptedClient:
    """Fake async httpx client replaying scripted results, per provider."""

    def __init__(self, results: list) -> None:
        self._results: list = list(results)
        self.calls: list[dict] = []

    async def post(self, url: str, **kwargs) -> ScriptedResponse:
        self.calls.append(kwargs.get("json") or {})
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        status_code, payload = result
        return ScriptedResponse(status_code, payload)


class FakeClock:
    """Deterministic injectable clock."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeGemini(BaseProvider):
    """Mock Gemini provider with scripted success/failure."""

    def __init__(self, text: str = "Gemini answered.") -> None:
        self._model = "gemini/mock"
        self._text = text
        self.calls = 0

    @property
    def model(self) -> str:
        return self._model

    async def generate(self, prompt, system_prompt=None, temperature=0.0,
                        max_tokens=1000, images=None) -> str:
        self.calls += 1
        return self._text


def build_chain(
    opencode_results: list,
    openrouter_results: list,
    gemini: FakeGemini | None = None,
    models: list[str] | None = None,
) -> tuple[ProviderManager, OpenCodeRotatingProvider, OpenRouterProvider, FakeGemini]:
    """Build the real priority chain over scripted HTTP clients."""
    clock = FakeClock()
    opencode = OpenCodeRotatingProvider(
        ModelPoolManager(list(models if models is not None else OC_MODELS)),
        cooldown_seconds=30.0,
        clock=clock,
    )
    opencode._client = ScriptedClient(opencode_results)

    openrouter = OpenRouterProvider(
        ModelPoolManager(["or-1:free"]), api_key="test-key", timeout=5
    )
    openrouter._client = ScriptedClient(openrouter_results)

    gemini = gemini or FakeGemini()
    manager = ProviderManager([opencode, openrouter, gemini])
    return manager, opencode, openrouter, gemini


async def _generate(manager: ProviderManager) -> LLMResponse:
    return await manager.generate("Hi")


def test_opencode_is_first_and_dynamic() -> bool:
    """Scenarios A+I: factory places OpenCode first, models from catalog."""
    captured: dict = {}
    discovered_base_urls: list = []

    def _record_openai_client(*args, **kwargs):
        # Both OpenCode discovery and OpenRouter discovery construct SDK
        # clients through this patched class; remember every base URL.
        discovered_base_urls.append(str(kwargs.get("base_url", "")))
        if "opencode.ai" in str(kwargs.get("base_url", "")):
            captured["opencode"] = True
            data = [
                SimpleNamespace(id=model_id, object="model", pricing=None)
                for model_id in CATALOG_IDS
            ]
        else:
            data = [
                SimpleNamespace(id="meta-llama/llama-3.3-70b-instruct:free",
                                object="model", pricing=None),
            ]
        return SimpleNamespace(models=SimpleNamespace(
            list=lambda: SimpleNamespace(data=data)
        ))

    original_priority = settings.provider_priority
    try:
        settings.provider_priority = "opencode,openrouter,gemini,groq"
        with patch(
            "app.services.llm.model_catalog.OpenAI",
            side_effect=_record_openai_client,
        ):
            manager = build_provider_manager()
    finally:
        settings.provider_priority = original_priority

    types = [type(provider).__name__ for provider in manager._providers]
    if not types or types[0] != "OpenCodeRotatingProvider":
        print(f"FAIL: OpenCode is not first in the chain: {types}")
        return False

    opencode = manager._providers[0]
    expected = ["oc-a-free", "oc-b-free", "oc-c-free"]
    pool_models = [opencode._pool.get_current_model()]
    opencode._pool.move_next()
    pool_models.append(opencode._pool.get_current_model())
    opencode._pool.move_next()
    pool_models.append(opencode._pool.get_current_model())
    if pool_models != expected:
        print(f"FAIL: pool not built dynamically from catalog: {pool_models}")
        return False
    if "claude-opus-5" in pool_models or "gpt-5.4" in pool_models:
        print(f"FAIL: paid models leaked into pool: {pool_models}")
        return False
    if not captured.get("opencode"):
        print(f"FAIL: OpenCode catalog endpoint never queried: {discovered_base_urls}")
        return False

    rest = types[1:]
    if "OpenRouterProvider" not in rest:
        print(f"FAIL: OpenRouter missing after OpenCode: {types}")
        return False
    if "GeminiProvider" not in rest and "FakeGemini" not in rest:
        print(f"FAIL: Gemini missing after OpenRouter: {types}")
        return False
    return True


def test_factory_skips_opencode_when_catalog_fails() -> bool:
    """Catalog failure at startup degrades gracefully instead of crashing."""
    original_priority = settings.provider_priority
    try:
        settings.provider_priority = "opencode,gemini"
        with patch(
            "app.services.llm.factory.build_opencode_pool_manager",
            side_effect=__import__(
                "app.services.llm.model_catalog", fromlist=["ModelCatalogError"]
            ).ModelCatalogError("catalog down"),
        ):
            manager = build_provider_manager()
    finally:
        settings.provider_priority = original_priority

    types = [type(provider).__name__ for provider in manager._providers]
    if "OpenCodeRotatingProvider" in types:
        print(f"FAIL: broken OpenCode still registered: {types}")
        return False
    if "GeminiProvider" not in types:
        print(f"FAIL: remaining providers lost: {types}")
        return False
    return True


def test_build_opencode_provider_uses_dynamic_pool() -> bool:
    """The standalone builder wires catalog -> pool -> rotating provider."""
    with patch(
        "app.services.llm.opencode_model_pool.OpenCodeModelCatalogService"
    ) as fake_service_cls:
        fake_service_cls.return_value.get_free_models.return_value = [
            "oc-b-free", "oc-a-free",
        ]
        provider = build_opencode_provider()

    if provider is None or not isinstance(provider, OpenCodeRotatingProvider):
        print("FAIL: builder returned no rotating provider")
        return False
    if provider.model != "oc-b-free":
        print(f"FAIL: unexpected first pool model: {provider.model}")
        return False
    if provider._pool.total_models() != 2:
        print(f"FAIL: pool size mismatch: {provider._pool.total_models()}")
        return False
    return True


def test_internal_rotation_before_failover() -> bool:
    """Scenario B+J: internal 429 rotation; OpenRouter never contacted."""
    manager, _, openrouter, gemini = build_chain(
        [(429, {}), completion("from oc-b")],
        [],  # any OpenRouter call would pop from empty -> loud failure
    )

    response = asyncio.run(_generate(manager))

    attempted = [call["model"] for call in manager._providers[0]._client.calls]
    if response.text != "from oc-b":
        print(f"FAIL: unexpected text {response.text!r}")
        return False
    if attempted != OC_MODELS[:2]:
        print(f"FAIL: unexpected internal attempts: {attempted}")
        return False
    if openrouter._client.calls:
        print("FAIL: OpenRouter was called despite OpenCode success")
        return False
    if gemini.calls:
        print("FAIL: Gemini was called despite OpenCode success")
        return False
    return True


def test_exhaustion_hands_off_to_openrouter() -> bool:
    """Scenarios C+D: exhausted OpenCode -> OpenRouter succeeds."""
    manager, opencode, openrouter, gemini = build_chain(
        [(429, {}), (503, {}), (503, {})],
        [completion("OpenRouter saved")],
    )

    response = asyncio.run(_generate(manager))

    if response.text != "OpenRouter saved":
        print(f"FAIL: unexpected text {response.text!r}")
        return False
    if len(opencode._client.calls) != len(OC_MODELS):
        print("FAIL: OpenCode did not attempt its whole pool first")
        return False
    if response.provider != "OpenRouterProvider":
        print(f"FAIL: unexpected provider name {response.provider!r}")
        return False
    if gemini.calls:
        print("FAIL: Gemini should not be reached")
        return False
    return True


def test_full_chain_failover_to_gemini() -> bool:
    """Scenario E: OpenCode + OpenRouter exhausted -> Gemini succeeds."""
    manager, _, openrouter, gemini = build_chain(
        [(429, {})] * len(OC_MODELS),
        [(500, {}), (500, {})],
    )

    response = asyncio.run(_generate(manager))

    if response.text != "Gemini answered.":
        print(f"FAIL: unexpected text {response.text!r}")
        return False
    if response.provider != "FakeGemini":
        print(f"FAIL: unexpected provider {response.provider!r}")
        return False
    if not openrouter._client.calls:
        print("FAIL: OpenRouter should have been tried before Gemini")
        return False
    return True


def test_opencode_success_skips_everything_else() -> bool:
    """Scenario F: healthy OpenCode answers; nobody else is called."""
    manager, _, openrouter, gemini = build_chain(
        [completion("first try works")],
        [],
    )

    response = asyncio.run(_generate(manager))

    if response.text != "first try works":
        print(f"FAIL: unexpected text {response.text!r}")
        return False
    if openrouter._client.calls or gemini.calls:
        print("FAIL: downstream providers were contacted unnecessarily")
        return False
    return True


def test_timeout_rotates_internally_not_to_openrouter() -> bool:
    """Scenario J: timeouts rotate inside OpenCode before any handoff."""
    import httpx

    four_models = ["oc-a-free", "oc-b-free", "oc-c-free", "oc-d-free"]
    manager, opencode, openrouter, _ = build_chain(
        [(429, {}), (503, {}), httpx.TimeoutException("hang"),
         completion("late but here")],
        [],
        models=four_models,
    )

    response = asyncio.run(_generate(manager))

    if response.text != "late but here":
        print(f"FAIL: unexpected text {response.text!r}")
        return False
    attempted = [call["model"] for call in opencode._client.calls]
    if attempted != four_models:
        print(f"FAIL: expected all four models rotated internally: {attempted}")
        return False
    if openrouter._client.calls:
        print("FAIL: single model failures leaked to OpenRouter")
        return False
    return True


def test_dead_model_skipped_across_requests() -> bool:
    """Scenario K: 404-dead OpenCode models are skipped on later requests."""
    results = [
        (404, {}),               # oc-a dies
        completion("b answers"), # request 1
        completion("c answers"), # request 2 (a skipped, b cooling? no - b ok)
    ]
    manager, opencode, openrouter, _ = build_chain(results, [])

    first = asyncio.run(_generate(manager))
    second = asyncio.run(_generate(manager))

    if first.text != "b answers" or second.text != "c answers":
        print(f"FAIL: unexpected responses {first.text!r} {second.text!r}")
        return False
    if not opencode.is_dead("oc-a-free"):
        print("FAIL: 404 model not marked dead")
        return False
    attempted = [call["model"] for call in opencode._client.calls]
    if attempted.count("oc-a-free") != 1:
        print(f"FAIL: dead model re-attempted: {attempted}")
        return False
    if openrouter._client.calls:
        print("FAIL: dead-model handling leaked to OpenRouter")
        return False
    return True


def test_llm_response_contract_unchanged() -> bool:
    """Scenario L: LLMResponse keeps provider/model/text semantics."""
    manager, _, _, _ = build_chain([completion("contract ok")], [])

    response = asyncio.run(_generate(manager))

    if not isinstance(response, LLMResponse):
        print(f"FAIL: wrong response type: {type(response).__name__}")
        return False
    if response.provider != "OpenCodeRotatingProvider":
        print(f"FAIL: provider field changed: {response.provider!r}")
        return False
    if response.model != "oc-a-free":
        print(f"FAIL: model field changed: {response.model!r}")
        return False
    if response.text != "contract ok":
        print(f"FAIL: text field changed: {response.text!r}")
        return False
    return True


def main() -> None:
    """Run all integration scenarios and report the overall result."""
    print("=" * 60)
    print("OpenCode Provider Integration Test")
    print("=" * 60)

    scenarios = [
        ("A+I. OpenCode first, dynamic catalog pool", test_opencode_is_first_and_dynamic),
        ("Graceful skip when OpenCode catalog fails", test_factory_skips_opencode_when_catalog_fails),
        ("Builder: catalog -> pool -> rotating provider", test_build_opencode_provider_uses_dynamic_pool),
        ("B+J. Internal rotation; OpenRouter untouched", test_internal_rotation_before_failover),
        ("C+D. Exhaustion -> OpenRouter succeeds", test_exhaustion_hands_off_to_openrouter),
        ("E. Full exhaustion -> Gemini succeeds", test_full_chain_failover_to_gemini),
        ("F. OpenCode success skips the rest", test_opencode_success_skips_everything_else),
        ("J. Timeout stays inside OpenCode", test_timeout_rotates_internally_not_to_openrouter),
        ("K. Dead model skipped across requests", test_dead_model_skipped_across_requests),
        ("L. LLMResponse contract unchanged", test_llm_response_contract_unchanged),
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
    print(f"Integration Test {'PASSED' if passed else 'FAILED'}")
    print("=" * 60)
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
