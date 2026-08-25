"""Deterministic unit tests for the OpenCode inference provider.

Verifies, without any network or live OpenCode calls:

- a successful completion returns the model's text
- the configured (dynamically supplied) model id is sent
- requests hit the OpenAI-compatible /chat/completions endpoint on the
  OpenCode inference base URL
- the prompt is sent as the user message (system prompt first when given)
- HTTP 400/404/5xx map to APIError with the status code preserved,
  HTTP 429 maps to RateLimitError, and auth rejections map to
  AuthenticationError
- timeouts surface as ProviderError
- malformed responses, missing choices, and missing/empty message content
  map to InvalidResponseError

Usage (from backend/):
    PYTHONPATH=. ../.venv/bin/python app/scripts/test_opencode_provider.py
"""

import asyncio
import json

import httpx

from app.services.llm.providers.base import (
    APIError,
    AuthenticationError,
    InvalidResponseError,
    ProviderError,
    RateLimitError,
)
from app.services.llm.providers.opencode import (
    OPENCODE_BASE_URL,
    OpenCodeProvider,
)

MODEL_ID = "mimo-v2.5-free"


class ScriptedResponse:
    """Minimal stand-in for httpx.Response used by the scripted client."""

    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload) if payload is not None else ""

    def json(self) -> dict:
        return self._payload


def completion(text: str) -> tuple[int, dict]:
    """Return a valid 200 OpenCode chat completion response."""
    return 200, {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "model": MODEL_ID,
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": text},
             "finish_reason": "stop"}
        ],
    }


class ScriptedClient:
    """A fake async client returning a queue of scripted results in order.

    Queue entries are ``(status_code, payload)`` tuples, Exception instances
    to raise instead, or pre-built ``ScriptedResponse`` objects.
    """

    def __init__(self, results: list) -> None:
        self._results: list = list(results)
        self.calls: list[dict] = []
        self.urls: list[str] = []

    async def post(
        self,
        url: str,
        *,
        headers: dict | None = None,
        json: dict | None = None,
    ) -> ScriptedResponse:
        self.urls.append(url)
        self.calls.append(json)
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        if isinstance(result, ScriptedResponse):
            return result
        status_code, payload = result
        return ScriptedResponse(status_code, payload)


def build_provider(results: list, model_id: str = MODEL_ID):
    """Build an OpenCodeProvider wired to a scripted (offline) client."""
    provider = OpenCodeProvider(model=model_id)
    provider._client = ScriptedClient(results)
    return provider


def test_successful_completion() -> bool:
    """A healthy response returns the assistant text."""
    provider = build_provider([completion("Hello from OpenCode!")])

    text = asyncio.run(provider.generate("Hi"))

    if text != "Hello from OpenCode!":
        print(f"FAIL: unexpected text: {text!r}")
        return False
    return True


def test_correct_model_and_endpoint() -> bool:
    """The supplied model id is sent to /chat/completions on the right base."""
    custom_model = "hy3-free"
    provider = build_provider([completion("ok")], model_id=custom_model)
    if provider.model != custom_model:
        print(f"FAIL: model property mismatch: {provider.model!r}")
        return False

    asyncio.run(provider.generate("Hi"))

    client = provider._client
    if len(client.calls) != 1:
        print(f"FAIL: expected exactly one request, got {len(client.calls)}")
        return False
    if client.urls[0] != "/chat/completions":
        print(f"FAIL: wrong endpoint path: {client.urls[0]!r}")
        return False
    sent = client.calls[0]
    if sent["model"] != custom_model:
        print(f"FAIL: wrong model id sent: {sent['model']!r}")
        return False
    # The real client must be constructed against the OpenCode base URL.
    live_client = OpenCodeProvider(model=custom_model)._client
    if str(live_client.base_url).rstrip("/") != OPENCODE_BASE_URL:
        print(f"FAIL: wrong base URL: {live_client.base_url}")
        return False
    return True


def test_prompt_flow() -> bool:
    """The built prompt is the user message; system prompt leads when given."""
    provider = build_provider([completion("ok")])

    asyncio.run(provider.generate("What is RAG?", system_prompt="Be concise."))

    messages = provider._client.calls[0]["messages"]
    expected = [
        {"role": "system", "content": "Be concise."},
        {"role": "user", "content": "What is RAG?"},
    ]
    if messages != expected:
        print(f"FAIL: unexpected messages: {messages}")
        return False

    provider = build_provider([completion("ok")])
    asyncio.run(provider.generate("Only user", temperature=0.7, max_tokens=256))
    payload = provider._client.calls[0]
    if payload["temperature"] != 0.7 or payload["max_tokens"] != 256:
        print(f"FAIL: sampling params not forwarded: {payload}")
        return False
    return True


def test_http_400() -> bool:
    """HTTP 400 (e.g. model unavailable) maps to APIError with code 400."""
    provider = build_provider([(400, {"error": "Model unavailable"})])

    try:
        asyncio.run(provider.generate("Hi"))
    except APIError as exc:
        if exc.status_code != 400:
            print(f"FAIL: wrong status code: {exc.status_code}")
            return False
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: expected APIError, got {type(exc).__name__}: {exc}")
        return False
    print("FAIL: HTTP 400 did not raise")
    return False


def test_http_404() -> bool:
    """HTTP 404 (dead/unknown model) maps to APIError with code 404."""
    provider = build_provider([(404, {"error": "Not found"})])

    try:
        asyncio.run(provider.generate("Hi"))
    except APIError as exc:
        if exc.status_code != 404:
            print(f"FAIL: wrong status code: {exc.status_code}")
            return False
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: expected APIError, got {type(exc).__name__}: {exc}")
        return False
    print("FAIL: HTTP 404 did not raise")
    return False


def test_http_429() -> bool:
    """HTTP 429 (free usage limit) maps to RateLimitError."""
    provider = build_provider([(429, {"error": "FreeUsageLimitError"})])

    try:
        asyncio.run(provider.generate("Hi"))
    except RateLimitError:
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: expected RateLimitError, got {type(exc).__name__}: {exc}")
        return False
    print("FAIL: HTTP 429 did not raise")
    return False


def test_http_5xx() -> bool:
    """HTTP 5xx (endpoint unavailable / upstream overloaded) maps to APIError."""
    for status_code in (500, 502, 503):
        provider = build_provider([(status_code, {"error": "boom"})])
        try:
            asyncio.run(provider.generate("Hi"))
        except APIError as exc:
            if exc.status_code != status_code:
                print(f"FAIL: {status_code} mapped to {exc.status_code}")
                return False
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL: expected APIError, got {type(exc).__name__}: {exc}")
            return False
        else:
            print(f"FAIL: HTTP {status_code} did not raise")
            return False
    return True


def test_auth_rejection() -> bool:
    """Auth rejections map to AuthenticationError like other providers."""
    for status_code in (401, 403):
        provider = build_provider([(status_code, {"error": "denied"})])
        try:
            asyncio.run(provider.generate("Hi"))
        except AuthenticationError:
            continue
        print(f"FAIL: HTTP {status_code} did not raise AuthenticationError")
        return False
    return True


def test_timeout() -> bool:
    """Network timeouts surface as ProviderError."""
    provider = build_provider([httpx.TimeoutException("timed out")])

    try:
        asyncio.run(provider.generate("Hi"))
    except ProviderError as exc:
        if "timed out" not in str(exc):
            print(f"FAIL: timeout context missing: {exc}")
            return False
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: expected ProviderError, got {type(exc).__name__}: {exc}")
        return False
    print("FAIL: timeout did not raise")
    return False


def test_malformed_response() -> bool:
    """Unparseable JSON or non-object payloads map to InvalidResponseError."""
    broken = ScriptedResponse(200)
    broken.json = lambda: (_ for _ in ()).throw(ValueError("invalid json"))
    cases: list = [
        ([broken], "unparseable json"),
        ([(200, ["not", "an", "object"])], "non-object payload"),
        ([(200, {"choices": "nope"})], "choices not a list"),
        ([(200, {})], "missing choices"),
        ([(200, {"choices": []})], "empty choices"),
        ([(200, {"choices": [{"message": {}}]})], "missing content"),
        ([(200, {"choices": [{"message": {"content": None}}]})], "null content"),
        ([(200, {"choices": [{"message": {"content": "   "}}]})], "blank content"),
        ([(200, {"choices": [{"message": {"content": 123}}]})], "non-string content"),
    ]
    for results, label in cases:
        provider = build_provider(results)
        try:
            asyncio.run(provider.generate("Hi"))
        except InvalidResponseError:
            continue
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL [{label}]: expected InvalidResponseError, "
                  f"got {type(exc).__name__}: {exc}")
            return False
        print(f"FAIL [{label}]: did not raise")
        return False
    return True


def test_streaming_default() -> bool:
    """Streaming works via the base single-chunk default implementation."""

    async def collect():
        provider = build_provider([completion("streamed text")])
        return [chunk async for chunk in provider.generate_stream("Hi")]

    chunks = asyncio.run(collect())
    if chunks != ["streamed text"]:
        print(f"FAIL: unexpected stream chunks: {chunks!r}")
        return False
    return True


def main() -> None:
    """Run all OpenCode provider scenarios and report the overall result."""
    print("=" * 60)
    print("OpenCode Provider Test")
    print("=" * 60)

    scenarios = [
        ("Success: completion returns text", test_successful_completion),
        ("Wiring: model id + endpoint + base URL", test_correct_model_and_endpoint),
        ("Prompt flow: user/system messages + params", test_prompt_flow),
        ("Errors: HTTP 400 -> APIError(400)", test_http_400),
        ("Errors: HTTP 404 -> APIError(404)", test_http_404),
        ("Errors: HTTP 429 -> RateLimitError", test_http_429),
        ("Errors: HTTP 5xx -> APIError(5xx)", test_http_5xx),
        ("Errors: auth rejection -> AuthenticationError", test_auth_rejection),
        ("Errors: timeout -> ProviderError", test_timeout),
        ("Robustness: malformed/missing content", test_malformed_response),
        ("Streaming: base default single chunk", test_streaming_default),
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
    print(f"OpenCode Provider Test {'PASSED' if passed else 'FAILED'}")
    print("=" * 60)
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
