"""Deterministic tests for the Agnes AI provider and factory wiring.

These tests NEVER touch the real Agnes API. The HTTP client is replaced with a
fake so we can assert request shape, error mapping, and ProviderManager
failover in isolation. The live smoke test is performed separately.
"""

import logging

import pytest

import app.services.llm.providers.agnes as agnes
from app.core.config import settings
from app.services.llm.factory import build_agnes_provider, build_provider_manager
from app.services.llm.provider_manager import ProviderManager
from app.services.llm.providers.agnes import AgnesProvider
from app.services.llm.providers.base import (
    APIError,
    AuthenticationError,
    BaseProvider,
    InvalidResponseError,
    ProviderError,
    RateLimitError,
)


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data
        self.text = text

    def json(self):
        if self._json is None:
            raise ValueError("no json body")
        return self._json


class FakeClient:
    def __init__(self, response):
        self._response = response
        self.calls = []

    async def post(self, url, headers=None, json=None):
        self.calls.append((url, headers, json))
        return self._response


def _provider(monkeypatch, response, api_key="test-key", model="agnes-2.5-flash"):
    client = FakeClient(response)
    monkeypatch.setattr(agnes.httpx, "AsyncClient", lambda *a, **k: client)
    provider = AgnesProvider(api_key=api_key, model=model, timeout=5)
    return provider, client


# ---------------------------------------------------------------------------
# Construction / configuration
# ---------------------------------------------------------------------------

def test_construction_and_model_property(monkeypatch):
    provider, _ = _provider(monkeypatch, FakeResponse())
    assert provider.model == "agnes-2.5-flash"


def test_api_key_comes_from_settings(monkeypatch):
    import app.services.llm.factory as factory

    monkeypatch.setattr(factory, "build_agnes_pool", lambda: ["agnes-2.5-flash"])
    original = settings.agnes_api_key
    settings.agnes_api_key = "from-settings-key"
    try:
        provider = build_agnes_provider()
        assert provider is not None
        assert provider._api_key == "from-settings-key"
    finally:
        settings.agnes_api_key = original


def test_factory_returns_none_without_api_key():
    original = settings.agnes_api_key
    settings.agnes_api_key = ""
    try:
        assert build_agnes_provider() is None
    finally:
        settings.agnes_api_key = original


# ---------------------------------------------------------------------------
# Request shape
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_correct_endpoint_and_model_sent(monkeypatch):
    provider, client = _provider(monkeypatch, FakeResponse(json_data=_ok("hi")))
    await provider.generate("hello")
    url, _headers, payload = client.calls[0]
    assert url == "/chat/completions"
    assert payload["model"] == "agnes-2.5-flash"


@pytest.mark.asyncio
async def test_prompt_and_system_prompt_sent(monkeypatch):
    provider, client = _provider(monkeypatch, FakeResponse(json_data=_ok("hi")))
    await provider.generate("the question", system_prompt="be precise")
    _url, _headers, payload = client.calls[0]
    messages = payload["messages"]
    assert messages[0] == {"role": "system", "content": "be precise"}
    assert messages[1] == {"role": "user", "content": "the question"}


@pytest.mark.asyncio
async def test_temperature_and_max_tokens_sent(monkeypatch):
    provider, client = _provider(monkeypatch, FakeResponse(json_data=_ok("hi")))
    await provider.generate("q", temperature=0.3, max_tokens=1200)
    _url, _headers, payload = client.calls[0]
    assert payload["temperature"] == 0.3
    assert payload["max_tokens"] == 1200


@pytest.mark.asyncio
async def test_images_none_produces_text_only_request(monkeypatch):
    provider, client = _provider(monkeypatch, FakeResponse(json_data=_ok("hi")))
    await provider.generate("q", images=None)
    _url, _headers, payload = client.calls[0]
    # No system prompt was supplied, so the user message is the only element.
    assert isinstance(payload["messages"][-1]["content"], str)


@pytest.mark.asyncio
async def test_images_forwarded_as_image_url_parts(monkeypatch):
    provider, client = _provider(monkeypatch, FakeResponse(json_data=_ok("hi")))
    images = [{"mime": "image/png", "data": "BASE64DATA"}]
    await provider.generate("describe", images=images)
    _url, _headers, payload = client.calls[0]
    content = payload["messages"][-1]["content"]
    assert isinstance(content, list)
    assert content[0] == {"type": "text", "text": "describe"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


# ---------------------------------------------------------------------------
# Response parsing / error mapping (existing provider contract)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_successful_response_parsed(monkeypatch):
    provider, _ = _provider(monkeypatch, FakeResponse(json_data=_ok("answer")))
    assert await provider.generate("q") == "answer"


@pytest.mark.asyncio
async def test_http_401_maps_to_authentication_error(monkeypatch):
    provider, _ = _provider(monkeypatch, FakeResponse(401, text="nope"))
    with pytest.raises(AuthenticationError):
        await provider.generate("q")


@pytest.mark.asyncio
async def test_http_429_maps_to_rate_limit_error(monkeypatch):
    provider, _ = _provider(monkeypatch, FakeResponse(429, text="slow"))
    with pytest.raises(RateLimitError):
        await provider.generate("q")


@pytest.mark.asyncio
async def test_http_500_maps_to_api_error(monkeypatch):
    provider, _ = _provider(monkeypatch, FakeResponse(500, text="boom"))
    with pytest.raises(APIError):
        await provider.generate("q")


@pytest.mark.asyncio
async def test_empty_content_maps_to_invalid_response(monkeypatch):
    provider, _ = _provider(
        monkeypatch, FakeResponse(json_data={"choices": [{"message": {"content": "  "}}]})
    )
    with pytest.raises(InvalidResponseError):
        await provider.generate("q")


@pytest.mark.asyncio
async def test_malformed_response_maps_to_invalid_response(monkeypatch):
    provider, _ = _provider(monkeypatch, FakeResponse(json_data={"unexpected": True}))
    with pytest.raises(InvalidResponseError):
        await provider.generate("q")


@pytest.mark.asyncio
async def test_transport_timeout_maps_to_provider_error(monkeypatch):
    import httpx

    client = FakeClient(None)

    async def _boom(*a, **k):
        raise httpx.TimeoutException("timed out")

    client.post = _boom
    monkeypatch.setattr(agnes.httpx, "AsyncClient", lambda *a, **k: client)
    provider = AgnesProvider(api_key="k", model="agnes-2.5-flash", timeout=5)
    with pytest.raises(ProviderError):
        await provider.generate("q")


# ---------------------------------------------------------------------------
# Failover through ProviderManager
# ---------------------------------------------------------------------------

class StubProvider(BaseProvider):
    def __init__(self, text):
        self._text = text

    @property
    def model(self):
        return "stub"

    async def generate(self, prompt, system_prompt=None, temperature=0.0,
                       max_tokens=1000, images=None):
        return self._text


@pytest.mark.asyncio
async def test_provider_manager_fails_over_after_agnes_error(monkeypatch):
    failing, _ = _provider(monkeypatch, FakeResponse(500, text="down"))
    pm = ProviderManager([failing, StubProvider("fallback-answer")])
    result = await pm.generate("q")
    assert result.text == "fallback-answer"


# ---------------------------------------------------------------------------
# Security: key must never leak into logs or errors
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_api_key_not_exposed_in_errors_or_logs(monkeypatch, caplog):
    secret = "super-secret-agnes-key-12345"
    provider, _ = _provider(
        monkeypatch, FakeResponse(500, text="server says nothing secret"),
        api_key=secret,
    )
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="app"):
        with pytest.raises(APIError) as excinfo:
            await provider.generate("q")
    assert secret not in str(excinfo.value)
    assert secret not in caplog.text


# ---------------------------------------------------------------------------
# Factory routing (existing providers unaffected)
# ---------------------------------------------------------------------------

def test_factory_includes_agnes_only_when_in_priority(monkeypatch):
    monkeypatch.setattr(settings, "provider_priority", "agnes,groq")
    monkeypatch.setattr(settings, "agnes_api_key", "k")
    _stub_factory(monkeypatch)
    pm = build_provider_manager()
    names = [type(p).__name__ for p in pm._providers]
    assert names == ["AgnesRotatingProvider", "StubProvider"]


def test_factory_excludes_agnes_when_not_in_priority(monkeypatch):
    monkeypatch.setattr(settings, "provider_priority", "openrouter,gemini,groq")
    monkeypatch.setattr(settings, "agnes_api_key", "")
    _stub_factory(monkeypatch)
    pm = build_provider_manager()
    assert all(type(p).__name__ != "AgnesProvider" for p in pm._providers)


def _stub_factory(monkeypatch):
    """Replace every builder except Agnes with harmless stubs so routing is
    deterministic and network-free. Agnes pool discovery is also stubbed so the
    factory does not hit the live models.dev catalog during routing tests."""
    import app.services.llm.factory as factory

    monkeypatch.setattr(factory, "build_opencode_provider", lambda: None)
    monkeypatch.setattr(factory, "build_openrouter_provider", lambda: StubProvider("or"))
    monkeypatch.setattr(factory, "build_gemini_provider", lambda: StubProvider("gm"))
    monkeypatch.setattr(factory, "build_groq_provider", lambda: StubProvider("gq"))
    monkeypatch.setattr(
        factory, "build_agnes_pool", lambda: ["agnes-2.0-flash", "agnes-2.5-flash"]
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok(text):
    return {"choices": [{"message": {"content": text}}]}
