"""Manual test for OpenRouterProvider internal model rotation.

Verifies that OpenRouterProvider advances ModelPoolManager and retries the
request with the next model on recoverable failures (rate limiting, temporary
server failure, timeout, model unavailability), while never retrying the same
model twice within one request and never rotating for authentication or
configuration errors. It also verifies that ProviderManager falls back to
Gemini once the OpenRouter pool is exhausted.

The HTTP layer is faked with a scripted client, so no network calls are made.
"""

import asyncio
import json
import logging

from app.services.llm.model_pool import ModelPoolManager
from app.services.llm.provider_manager import ProviderManager
from app.services.llm.providers.base import (
    AuthenticationError,
    BaseProvider,
    ProviderError,
)
from app.services.llm.providers.openrouter import OpenRouterProvider

MODELS = ["model-1", "model-2", "model-3"]


class ScriptedResponse:
    """Minimal stand-in for httpx.Response used by the scripted client."""

    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload) if payload is not None else ""

    def json(self) -> dict:
        return self._payload


class ScriptedClient:
    """A fake async client returning a queue of responses in call order."""

    def __init__(self, responses: list[tuple[int, dict | None]]) -> None:
        self._responses: list[tuple[int, dict | None]] = list(responses)
        self.calls: list[dict] = []

    async def post(
        self,
        url: str,
        *,
        headers: dict | None = None,
        json: dict | None = None,
    ) -> ScriptedResponse:
        self.calls.append(json)
        status_code, payload = self._responses.pop(0)
        return ScriptedResponse(status_code, payload)


def success_response(text: str) -> tuple[int, dict]:
    """Return a valid 200 OpenRouter chat completion response."""
    return 200, {
        "choices": [{"message": {"role": "assistant", "content": text}}]
    }


def build_provider(
    responses: list[tuple[int, dict | None]],
    models: list[str] | None = None,
) -> tuple[OpenRouterProvider, ModelPoolManager]:
    """Build an OpenRouterProvider backed by a scripted HTTP client."""
    if models is None:
        models = list(MODELS)
    pool = ModelPoolManager(models)
    provider = OpenRouterProvider(pool, api_key="test-key")
    provider._client = ScriptedClient(responses)
    return provider, pool


def attempted_models(provider: OpenRouterProvider) -> list[str]:
    """Return the model ids tried, in request order."""
    return [call["model"] for call in provider._client.calls]


class MockGemini(BaseProvider):
    """Mock Gemini provider that always succeeds."""

    def __init__(self) -> None:
        self._model = "gemini/mock"

    @property
    def model(self) -> str:
        return self._model

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> str:
        return "Failover succeeded via Gemini (simulated)."


async def test_first_model_succeeds() -> bool:
    """Test A: Model 1 succeeds; Model 2 must not be called."""
    provider, pool = build_provider([success_response("hello")])

    text = await provider.generate("Hi")

    calls = attempted_models(provider)
    if text != "hello":
        print("FAIL: unexpected response text")
        return False
    if calls != ["model-1"]:
        print(f"FAIL: expected only [model-1], got {calls}")
        return False
    if pool.get_current_model() != "model-1":
        print("FAIL: pool should not have advanced on success")
        return False
    return True


async def test_first_fails_second_succeeds() -> bool:
    """Test B: Model 1 rate-limited, Model 2 succeeds."""
    provider, pool = build_provider([(429, {}), success_response("ok")])

    text = await provider.generate("Hi")

    calls = attempted_models(provider)
    if text != "ok":
        print("FAIL: expected the second model's response")
        return False
    if calls != ["model-1", "model-2"]:
        print(f"FAIL: expected attempts [model-1, model-2], got {calls}")
        return False
    if pool.get_current_model() != "model-2":
        print("FAIL: pool should have advanced to model-2")
        return False
    return True


async def test_all_models_fail() -> bool:
    """Test C: every model fails; each attempted once; pool exhausted."""
    provider, pool = build_provider(
        [(500, {}), (500, {}), (500, {})]
    )

    try:
        await provider.generate("Hi")
        print("FAIL: expected ProviderError after exhaustion")
        return False
    except ProviderError:
        pass

    calls = attempted_models(provider)
    if calls != ["model-1", "model-2", "model-3"]:
        print(f"FAIL: expected each model exactly once, got {calls}")
        return False

    try:
        pool.move_next()
        print("FAIL: pool should be exhausted")
        return False
    except RuntimeError:
        pass
    return True


async def test_auth_error_does_not_rotate() -> bool:
    """Test D: authentication error must not rotate through the pool."""
    provider, _ = build_provider(
        [(401, {}), success_response("never reached")]
    )

    try:
        await provider.generate("Hi")
        print("FAIL: expected AuthenticationError")
        return False
    except AuthenticationError:
        pass

    calls = attempted_models(provider)
    if calls != ["model-1"]:
        print(f"FAIL: auth error must only attempt one model, got {calls}")
        return False
    return True


async def test_config_error_does_not_rotate() -> bool:
    """Permanent configuration error (402 insufficient credits) must not rotate."""
    provider, _ = build_provider(
        [(402, {}), (403, {}), success_response("never reached")]
    )

    try:
        await provider.generate("Hi")
        print("FAIL: expected ProviderError on configuration error")
        return False
    except ProviderError:
        pass

    calls = attempted_models(provider)
    if calls != ["model-1"]:
        print(f"FAIL: config error must only attempt one model, got {calls}")
        return False
    return True


async def test_fallback_to_gemini_after_pool_exhausted() -> bool:
    """Pool exhausted -> ProviderManager falls back to Gemini."""
    openrouter_provider, pool = build_provider(
        [(500, {}), (500, {}), (500, {})]
    )
    gemini = MockGemini()
    manager = ProviderManager([openrouter_provider, gemini])

    response = await manager.generate("Hi")

    if response.provider != "MockGemini":
        print(f"FAIL: expected MockGemini to win, got {response.provider}")
        return False
    if attempted_models(openrouter_provider) != ["model-1", "model-2", "model-3"]:
        print("FAIL: OpenRouter should have attempted every model once")
        return False
    if pool.get_current_model() != "model-3":
        print("FAIL: pool should remain exhausted at model-3")
        return False
    return True


async def main() -> None:
    """Run all rotation scenarios and report the overall result."""
    logging.getLogger("app.services.llm.provider_manager").setLevel(
        logging.CRITICAL
    )

    print("=" * 60)
    print("OpenRouter Model Rotation Test")
    print("=" * 60)

    scenarios = [
        ("Test A: Model 1 succeeds -> return immediately", test_first_model_succeeds),
        (
            "Test B: Model 1 fails, Model 2 succeeds -> rotate once",
            test_first_fails_second_succeeds,
        ),
        (
            "Test C: all models fail -> each tried once, pool exhausted",
            test_all_models_fail,
        ),
        (
            "Test D: auth error -> no rotation",
            test_auth_error_does_not_rotate,
        ),
        (
            "Test E: config error (402) -> no rotation",
            test_config_error_does_not_rotate,
        ),
        (
            "Test F: pool exhausted -> Gemini fallback",
            test_fallback_to_gemini_after_pool_exhausted,
        ),
    ]

    passed = True
    for label, scenario in scenarios:
        print()
        print(label)
        result = await scenario()
        print("PASSED" if result else "FAILED")
        passed = passed and result

    print()
    print("=" * 60)
    print(f"Rotation Test {'PASSED' if passed else 'FAILED'}")
    print("=" * 60)
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())