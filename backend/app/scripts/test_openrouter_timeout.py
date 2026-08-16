"""Deterministic regression tests for OpenRouter timeout and failover behavior.

Verifies, without any network calls:

- a slow/hung attempt is abandoned after a bounded per-attempt timeout and the
  request rotates to the next model
- the total time budget bounds the whole OpenRouter pass and hands off to the
  next provider, keeping failover intact
- models that return 404 (no endpoint) are remembered as unavailable and
  skipped on subsequent requests

Usage (from backend/):
    PYTHONPATH=. ../.venv/bin/python app/scripts/test_openrouter_timeout.py
"""

import asyncio
import json
import time

from app.services.llm.model_pool import ModelPoolManager
from app.services.llm.provider_manager import ProviderManager
from app.services.llm.providers.base import BaseProvider, ProviderError
from app.services.llm.providers.openrouter import OpenRouterProvider

HANG = ("HANG", None)


class ScriptedResponse:
    """Minimal stand-in for httpx.Response used by the scripted client."""

    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload) if payload is not None else ""

    def json(self) -> dict:
        return self._payload


class ScriptedClient:
    """A fake async client. ``("HANG", None)`` blocks until cancelled."""

    def __init__(self, responses: list[tuple]) -> None:
        self._responses: list[tuple] = list(responses)
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
        if status_code == "HANG":
            await asyncio.sleep(60)
            raise AssertionError("hanging response was not cancelled")
        return ScriptedResponse(status_code, payload)


def success_response(text: str = "ok") -> tuple:
    """Return a valid 200 OpenRouter chat completion response."""
    return 200, {"choices": [{"message": {"role": "assistant", "content": text}}]}


def build_provider(
    models: list[str],
    responses: list[tuple],
    attempt_timeout: float = 0.05,
    total_timeout: float = 1.0,
) -> tuple[OpenRouterProvider, ModelPoolManager]:
    """Build an OpenRouterProvider with small, injectable timeouts."""
    pool = ModelPoolManager(models)
    provider = OpenRouterProvider(
        pool,
        api_key="test-key",
        attempt_timeout=attempt_timeout,
        total_timeout=total_timeout,
    )
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


async def test_slow_attempt_times_out_and_rotates() -> bool:
    """A hung model is abandoned at the per-attempt timeout; rotation continues."""
    provider, _ = build_provider(
        ["slow-model", "fast-model"],
        [HANG, success_response()],
        attempt_timeout=0.05,
        total_timeout=5.0,
    )
    start = time.monotonic()
    text = await provider.generate("Hi")
    elapsed = time.monotonic() - start

    calls = attempted_models(provider)
    if text != "ok":
        print("FAIL: unexpected response text")
        return False
    if calls != ["slow-model", "fast-model"]:
        print(f"FAIL: expected rotation [slow-model, fast-model], got {calls}")
        return False
    if elapsed >= 1.0:
        print(f"FAIL: per-attempt timeout not bounded (elapsed {elapsed:.2f}s)")
        return False
    return True


async def test_total_budget_hands_off_to_next_provider() -> bool:
    """The total budget bounds OpenRouter; ProviderManager fails over to Gemini."""
    models = ["m1", "m2", "m3", "m4", "m5"]
    provider, _ = build_provider(
        models,
        [HANG] * len(models),
        attempt_timeout=0.05,
        total_timeout=0.12,
    )
    manager = ProviderManager([provider, MockGemini()])
    start = time.monotonic()
    response = await manager.generate("Hi")
    elapsed = time.monotonic() - start

    calls = attempted_models(provider)
    if response.provider != "MockGemini":
        print(f"FAIL: expected failover to MockGemini, got {response.provider}")
        return False
    if not calls or len(calls) >= len(models):
        print(f"FAIL: total budget should stop before all models, got {len(calls)}")
        return False
    if elapsed >= 1.0:
        print(f"FAIL: total budget not bounded (elapsed {elapsed:.2f}s)")
        return False
    return True


async def test_404_models_skipped_on_subsequent_calls() -> bool:
    """A 404 model is remembered as dead and skipped on later requests."""
    provider, pool = build_provider(
        ["model-a", "model-b"],
        [(404, {}), success_response(), success_response()],
        attempt_timeout=0.05,
        total_timeout=5.0,
    )

    await provider.generate("Hi")
    first_call = attempted_models(provider)

    pool.reset()
    before = len(provider._client.calls)
    await provider.generate("Hi")
    second_call = attempted_models(provider)[before:]

    if first_call != ["model-a", "model-b"]:
        print(f"FAIL: first call unexpected, got {first_call}")
        return False
    if "model-a" in second_call:
        print(f"FAIL: dead model 'model-a' was retried: {second_call}")
        return False
    return True


async def test_404_does_not_break_exhaustion() -> bool:
    """404s do not bypass the pool; exhaustion still raises ProviderError."""
    provider, _ = build_provider(
        ["model-a"],
        [(404, {})],
        attempt_timeout=0.05,
        total_timeout=0.5,
    )
    try:
        await provider.generate("Hi")
        print("FAIL: expected ProviderError after pool exhaustion")
        return False
    except ProviderError:
        pass
    return True


async def main() -> None:
    """Run all timeout scenarios and report the overall result."""
    print("=" * 60)
    print("OpenRouter Timeout / Failover Test")
    print("=" * 60)

    scenarios = [
        ("Per-attempt timeout abandons slow model", test_slow_attempt_times_out_and_rotates),
        ("Total budget hands off to next provider", test_total_budget_hands_off_to_next_provider),
        ("404 models skipped on subsequent calls", test_404_models_skipped_on_subsequent_calls),
        ("404 exhaustion still raises ProviderError", test_404_does_not_break_exhaustion),
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
    print(f"OpenRouter Timeout Test {'PASSED' if passed else 'FAILED'}")
    print("=" * 60)
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())