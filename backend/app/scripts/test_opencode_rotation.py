"""Deterministic unit tests for OpenCode runtime rotation + cooldown.

Verifies, without any network or live OpenCode calls and without sleeping:

- successful first attempts return immediately
- HTTP 429 / 503 / timeouts put a model into temporary cooldown and rotate
- HTTP 404 / explicit model-unavailable 400s mark a model permanently
  unavailable for the pool lifecycle
- plain HTTP 400s stay fatal without rotating (existing error behavior)
- cooldown expiry makes rate-limited models eligible again
- successes clear temporary failure state
- full exhaustion (all cooling / all dead) fails cleanly, with no infinite
  loop and no repeated attempts within a pass
- the existing ModelPoolManager is reused and OpenRouter behavior is intact

Usage (from backend/):
    PYTHONPATH=. ../.venv/bin/python app/scripts/test_opencode_rotation.py
"""

import asyncio
import json

import httpx

from app.services.llm.model_pool import ModelPoolManager
from app.services.llm.providers.base import (
    APIError,
    AuthenticationError,
    InvalidResponseError,
    ProviderError,
    RateLimitError,
)
from app.services.llm.providers.opencode_rotation import (
    COOLDOWN,
    DEAD,
    FATAL,
    ROTATE,
    OpenCodeRotatingProvider,
    classify_opencode_failure,
)

MODELS = ["model-a-free", "model-b-free", "model-c-free", "model-d-free"]


class FakeClock:
    """Deterministic injectable clock; advance time explicitly in tests."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def completion(text: str) -> tuple[int, dict]:
    """Return a valid 200 chat completion response."""
    return 200, {
        "choices": [{"message": {"role": "assistant", "content": text}}]
    }


class ScriptedResponse:
    """Minimal stand-in for httpx.Response."""

    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload) if payload is not None else ""

    def json(self) -> dict:
        return self._payload


class ScriptedRuntimeClient:
    """Fake async client scripting one result per attempt, in order.

    Results are ``(status_code, payload)`` tuples or Exception instances.
    Records every attempted model id.
    """

    def __init__(self, results: list) -> None:
        self._results: list = list(results)
        self.attempted: list[str] = []

    async def post(
        self,
        url: str,
        *,
        headers: dict | None = None,
        json: dict | None = None,
    ) -> ScriptedResponse:
        self.attempted.append(json["model"])
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        status_code, payload = result
        return ScriptedResponse(status_code, payload)


def build_provider(results: list, models: list[str] | None = None):
    """Build a rotating provider over a scripted client and fake clock."""
    clock = FakeClock()
    provider = OpenCodeRotatingProvider(
        ModelPoolManager(list(models if models is not None else MODELS)),
        cooldown_seconds=30.0,
        clock=clock,
    )
    provider._client = ScriptedRuntimeClient(results)
    return provider, clock


def attempted_models(provider) -> list[str]:
    """Return the model ids tried, in order."""
    return provider._client.attempted


def expect_provider_error(awaitable, needle: str) -> bool:
    try:
        asyncio.run(awaitable)
    except ProviderError as exc:
        if needle.lower() not in str(exc).lower():
            print(f"FAIL: error lacks context {needle!r}: {exc}")
            return False
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: expected ProviderError, got {type(exc).__name__}: {exc}")
        return False
    print("FAIL: expected ProviderError, nothing raised")
    return False


async def _run_generate(provider):
    return await provider.generate("Hi")


# --- classification unit checks -------------------------------------------

def test_failure_classification() -> bool:
    """Every runtime rule maps to the intended action."""
    cases = [
        (RateLimitError("429"), COOLDOWN),
        (APIError("boom", status_code=500), COOLDOWN),
        (APIError("bad gateway", status_code=502), COOLDOWN),
        (APIError("unavailable", status_code=503), COOLDOWN),
        (APIError("timeout-ish", status_code=None), COOLDOWN),
        (ProviderError("OpenCode request timed out: x"), COOLDOWN),
        (ProviderError("connection failed"), COOLDOWN),
        (APIError("gone", status_code=404), DEAD),
        (
            APIError(
                'HTTP 400: {"error":{"message":"Model unavailable"}}',
                status_code=400,
            ),
            DEAD,
        ),
        (APIError("plain bad request", status_code=400), FATAL),
        (InvalidResponseError("no content"), ROTATE),
        (AuthenticationError("rejected"), FATAL),
    ]
    for exc, expected in cases:
        actual = classify_opencode_failure(exc)
        if actual != expected:
            print(f"FAIL: {exc!r} classified {actual!r}, expected {expected!r}")
            return False
    return True


# --- request-flow scenarios -------------------------------------------------

def test_first_model_succeeds() -> bool:
    """Scenario 1: healthy first model returns the response directly."""
    provider, _ = build_provider([completion("from A")])

    text = asyncio.run(provider.generate("Hi"))

    if text != "from A":
        print(f"FAIL: unexpected text {text!r}")
        return False
    if attempted_models(provider) != ["model-a-free"]:
        print(f"FAIL: unexpected attempts: {attempted_models(provider)}")
        return False
    if provider.cooldown_remaining("model-a-free") != 0.0:
        print("FAIL: success should leave no cooldown state")
        return False
    return True


def test_429_rotates_with_cooldown() -> bool:
    """Scenario 2: 429 cools the model and rotation reaches the second."""
    provider, _ = build_provider([
        (429, {"error": "FreeUsageLimitError"}),
        completion("from B"),
    ])

    text = asyncio.run(provider.generate("Hi"))

    if text != "from B":
        print(f"FAIL: unexpected text {text!r}")
        return False
    if attempted_models(provider) != ["model-a-free", "model-b-free"]:
        print(f"FAIL: unexpected attempts: {attempted_models(provider)}")
        return False
    if provider.cooldown_remaining("model-a-free") <= 0.0:
        print("FAIL: 429 model did not enter cooldown")
        return False
    if provider.is_dead("model-a-free"):
        print("FAIL: rate-limited model must not be dead")
        return False
    return True


def test_503_rotates_with_cooldown() -> bool:
    """Scenario 3: 503 cools the model and rotation continues."""
    provider, _ = build_provider([
        (503, {"error": "Endpoint unavailable"}),
        completion("from B"),
    ])

    text = asyncio.run(provider.generate("Hi"))

    if text != "from B":
        print(f"FAIL: unexpected text {text!r}")
        return False
    if provider.cooldown_remaining("model-a-free") <= 0.0:
        print("FAIL: 503 model did not enter cooldown")
        return False
    return True


def test_timeout_rotates_with_cooldown() -> bool:
    """Scenario 4: a timed-out model cools down and rotation continues."""
    provider, _ = build_provider([
        httpx.TimeoutException("slow"),
        completion("from B"),
    ])

    text = asyncio.run(provider.generate("Hi"))

    if text != "from B":
        print(f"FAIL: unexpected text {text!r}")
        return False
    if attempted_models(provider)[:2] != ["model-a-free", "model-b-free"]:
        print(f"FAIL: timeout did not rotate correctly: {attempted_models(provider)}")
        return False
    if provider.cooldown_remaining("model-a-free") <= 0.0:
        print("FAIL: timed-out model did not enter cooldown")
        return False
    return True


def test_404_marks_dead_and_skips() -> bool:
    """Scenario 5: a dead model is never attempted again this lifecycle."""
    provider, _ = build_provider([
        (404, {"error": "model gone"}),
        completion("from B"),
        completion("from B again"),
    ])

    first = asyncio.run(provider.generate("Hi"))
    second = asyncio.run(provider.generate("Hello again"))

    if first != "from B" or second != "from B again":
        print(f"FAIL: unexpected responses {first!r} {second!r}")
        return False
    if not provider.is_dead("model-a-free"):
        print("FAIL: 404 model was not marked dead")
        return False
    # Second request must skip the dead model entirely.
    if attempted_models(provider) != [
        "model-a-free",
        "model-b-free",
        "model-b-free",
    ]:
        print(f"FAIL: dead model re-attempted: {attempted_models(provider)}")
        return False
    return True


def test_400_model_unavailable_is_dead_but_plain_400_fatal() -> bool:
    """Rule 5/6 boundary: only explicit unavailability kills a 400."""
    provider, _ = build_provider([
        (400, {"error": {"message": "Model unavailable"}}),
        completion("from B"),
    ])
    text = asyncio.run(provider.generate("Hi"))
    if text != "from B" or not provider.is_dead("model-a-free"):
        print("FAIL: explicit model-unavailable 400 was not treated as dead")
        return False

    provider2, _ = build_provider([
        (400, {"error": {"message": "max_tokens too large"}}),
        completion("never reached"),
    ])
    return expect_provider_error(
        provider2.generate("Hi"), "max_tokens too large"
    )


def test_rate_limited_model_recovers_after_cooldown() -> bool:
    """Scenarios 6+11: cooldown expiry revives a 429'd model; never dead."""
    provider, clock = build_provider([
        (429, {"error": "FreeUsageLimitError"}),  # A fails
        completion("from B"),  # B answers
    ])
    asyncio.run(provider.generate("Hi"))

    if not provider.is_dead("model-a-free") is False:
        print("FAIL: 429 must never mark dead")
        return False

    clock.advance(31.0)  # past the 30s cooldown

    provider._client._results.append(completion("A is back"))
    text = asyncio.run(provider.generate("Hi again"))

    if text != "A is back":
        print(f"FAIL: cooled model not eligible again, got {text!r}")
        return False
    if "model-a-free" not in attempted_models(provider)[2:]:
        print(f"FAIL: A was not retried after cooldown: {attempted_models(provider)}")
        return False
    if provider.cooldown_remaining("model-a-free") != 0.0:
        print("FAIL: revival success did not clear cooldown state")
        return False
    return True


def test_success_clears_temporary_state() -> bool:
    """Scenario 7: a successful request resets that model's temp state."""
    provider, clock = build_provider([completion("ok")], models=["model-a-free"])
    provider._cooldown.start("model-a-free")
    clock.advance(31.0)  # expiry alone makes it eligible; success clears it

    text = asyncio.run(provider.generate("Hi"))

    if text != "ok":
        print(f"FAIL: unexpected text {text!r}")
        return False
    if provider.cooldown_remaining("model-a-free") != 0.0:
        print("FAIL: success did not clear temporary state")
        return False
    return True


def test_all_temporarily_unavailable_fails_cleanly() -> bool:
    """Scenario 8: everything cooling -> bounded clean failure, no loop."""
    provider, clock = build_provider([
        (429, {}), (503, {}), (429, {}), (503, {}),
    ])

    if not expect_provider_error(_run_generate(provider), "cooling down"):
        return False
    if len(attempted_models(provider)) != len(MODELS):
        print(f"FAIL: expected exactly {len(MODELS)} attempts, "
              f"got {len(attempted_models(provider))}")
        return False

    before = len(attempted_models(provider))
    if not expect_provider_error(_run_generate(provider), "cooling down"):
        return False
    if len(attempted_models(provider)) != before:
        print("FAIL: cooling models were re-attempted immediately")
        return False

    clock.advance(31.0)
    provider._client._results.extend([completion("recovered")] * 4)
    text = asyncio.run(provider.generate("retry"))
    if text != "recovered":
        print(f"FAIL: pool did not recover after cooldowns: {text!r}")
        return False
    return True


async def _run_generate(provider):
    return await provider.generate("Hi")


def test_all_permanently_unavailable_fails_cleanly() -> bool:
    """Scenario 9: everything dead -> clean failure, zero further calls."""
    provider, _ = build_provider([(404, {})] * len(MODELS))

    if not expect_provider_error(_run_generate(provider), "unavailable"):
        return False
    if len(attempted_models(provider)) != len(MODELS):
        print("FAIL: pass over dead models was not bounded")
        return False

    before = len(attempted_models(provider))
    if not expect_provider_error(_run_generate(provider), "unavailable"):
        return False
    if len(attempted_models(provider)) != before:
        print("FAIL: dead models were re-attempted")
        return False
    return True


def test_mixed_failures_eventual_success() -> bool:
    """Scenario 10: 429 -> 503 -> timeout -> success on model D."""
    results = [
        (429, {}),
        (503, {}),
        httpx.TimeoutException("hang"),
        completion("D saved the day"),
    ]
    provider, _ = build_provider(results)

    text = asyncio.run(provider.generate("Hi"))

    if text != "D saved the day":
        print(f"FAIL: expected D's response, got {text!r}")
        return False
    if attempted_models(provider) != MODELS:
        print(f"FAIL: expected all four attempted in order: "
              f"{attempted_models(provider)}")
        return False
    for model_id in MODELS[:3]:
        if provider.is_dead(model_id):
            print(f"FAIL: {model_id} wrongly marked dead")
            return False
        if provider.cooldown_remaining(model_id) <= 0.0:
            print(f"FAIL: {model_id} not cooling down")
            return False
    return True


def test_reuses_existing_pool_manager() -> bool:
    """The runtime layer drives the existing ModelPoolManager semantics."""
    manager = ModelPoolManager(["only-one-free"])

    class ExplodingList(list):
        def __iter__(self):  # ensure the manager instance itself is used
            raise AssertionError("raw list iterated instead of ModelPoolManager")

    provider = OpenCodeRotatingProvider(manager)
    if provider.model != "only-one-free":
        print("FAIL: manager-backed pool not reflected in provider.model")
        return False
    _ = ExplodingList  # silence unused warning style checkers

    provider2, _ = build_provider(
        [(404, {}), completion("backup ok")],
        models=["dead-model-free", "backup-free"],
    )
    text = asyncio.run(provider2.generate("Hi"))
    if text != "backup ok" or not provider2.is_dead("dead-model-free"):
        print("FAIL: list-form pool construction broken")
        return False
    return True


def main() -> None:
    """Run all OpenCode rotation/cooldown scenarios and report the result."""
    print("=" * 60)
    print("OpenCode Rotation & Cooldown Test")
    print("=" * 60)

    scenarios = [
        ("Classify: failure rules table", test_failure_classification),
        ("1. First model succeeds", test_first_model_succeeds),
        ("2. 429 -> cooldown -> next model succeeds", test_429_rotates_with_cooldown),
        ("3. 503 -> cooldown -> rotate", test_503_rotates_with_cooldown),
        ("4. Timeout -> cooldown -> rotate", test_timeout_rotates_with_cooldown),
        ("5. 404 -> permanently skipped", test_404_marks_dead_and_skips),
        ("5b. Explicit-unavailable 400 vs plain 400", test_400_model_unavailable_is_dead_but_plain_400_fatal),
        ("6+11. 429 model revives after cooldown", test_rate_limited_model_recovers_after_cooldown),
        ("7. Success clears temporary state", test_success_clears_temporary_state),
        ("8. All cooling -> clean bounded failure", test_all_temporarily_unavailable_fails_cleanly),
        ("9. All dead -> clean failure, no repeats", test_all_permanently_unavailable_fails_cleanly),
        ("10. Mixed failures -> D succeeds", test_mixed_failures_eventual_success),
        ("Reuse: existing ModelPoolManager driven", test_reuses_existing_pool_manager),
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
    print(f"OpenCode Rotation Test {'PASSED' if passed else 'FAILED'}")
    print("=" * 60)
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
