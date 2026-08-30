"""Tests for the Agnes rotating provider health/rotation logic.

Network-free: the httpx client is replaced with a fake that returns a
pre-programmed response per model id. Covers the required selection pipeline:
cached pool -> healthy candidates -> prefer previously-successful -> prefer low
latency -> deterministic tie-break -> ONE request, with success recording
health/latency and failure applying cooldown/dead, plus the clearly-separate
configured fallback model.
"""

import pytest

import app.services.llm.providers.agnes_rotation as ar
from app.services.llm.providers.agnes_rotation import AgnesRotatingProvider


class Resp:
    def __init__(self, status=200, content="ok", text=""):
        self.status_code = status
        self._content = content
        self.text = text

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


class FakeClient:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    async def post(self, url, headers=None, json=None, **kwargs):
        model_id = json["model"]
        self.calls.append(model_id)
        return self.handler(model_id)

    async def aclose(self):
        return None


class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def _make(handler, models, fallback="agnes-fallback", clock=None):
    """Return an AgnesRotatingProvider wired to a fake client."""
    fc = FakeClient(handler)
    ar.httpx.AsyncClient = lambda *a, **k: fc
    clock = clock or _Clock()
    p = AgnesRotatingProvider(
        api_key="k", models=models, fallback_model=fallback, clock=clock
    )
    return p, fc


def _ok(text="ok"):
    return lambda m: Resp(200, content=text)


@pytest.mark.asyncio
async def test_success_first_request_records_health():
    p, fc = _make(_ok("hi"), ["model-a", "model-b"])
    assert await p.generate("q") == "hi"
    # Deterministic tie-break (alphabetical) picked model-a first.
    assert fc.calls == ["model-a"]
    assert "model-a" in p._ever_successful
    assert p.model == "model-a"


@pytest.mark.asyncio
async def test_skips_cooling_down_model():
    p, fc = _make(_ok("ok"), ["model-a", "model-b"])
    p._cooldown.start("model-a")
    assert await p.generate("q") == "ok"
    assert fc.calls == ["model-b"]


@pytest.mark.asyncio
async def test_error_429_causes_cooldown_then_advance():
    def handler(m):
        if m == "model-a":
            return Resp(429)
        return Resp(200, content="from-b")

    p, fc = _make(handler, ["model-a", "model-b"])
    assert await p.generate("q") == "from-b"
    assert fc.calls == ["model-a", "model-b"]
    assert p.cooldown_remaining("model-a") > 0.0


@pytest.mark.asyncio
async def test_5xx_causes_cooldown():
    def handler(m):
        if m == "model-a":
            return Resp(500)
        return Resp(200, content="from-b")

    p, fc = _make(handler, ["model-a", "model-b"])
    assert await p.generate("q") == "from-b"
    assert p.cooldown_remaining("model-a") > 0.0


@pytest.mark.asyncio
async def test_model_unavailable_marked_dead():
    def handler(m):
        if m == "model-a":
            return Resp(404, text="model not found")
        return Resp(200, content="from-b")

    p, fc = _make(handler, ["model-a", "model-b"])
    assert await p.generate("q") == "from-b"
    assert p.is_dead("model-a")
    assert p.cooldown_remaining("model-a") == 0.0  # dead, not cooling


@pytest.mark.asyncio
async def test_400_model_unavailable_marked_dead():
    from app.services.llm.providers.base import APIError

    def handler(m):
        if m == "model-a":
            raise APIError("Model is unavailable", status_code=400)
        return Resp(200, content="from-b")

    p, _ = _make(handler, ["model-a", "model-b"])
    assert await p.generate("q") == "from-b"
    assert p.is_dead("model-a")


@pytest.mark.asyncio
async def test_auth_failure_is_fatal():
    from app.services.llm.providers.base import AuthenticationError

    def handler(m):
        raise AuthenticationError("bad key")

    p, fc = _make(handler, ["model-a", "model-b"])
    with pytest.raises(AuthenticationError):
        await p.generate("q")
    assert fc.calls == ["model-a"]


@pytest.mark.asyncio
async def test_prefers_low_latency():
    p, fc = _make(_ok(), ["model-a", "model-b"])
    # Record latency: model-a slow, model-b fast, both previously successful.
    p._ever_successful.update({"model-a", "model-b"})
    p._latency["model-a"] = 5.0
    p._latency["model-b"] = 1.0
    assert await p.generate("q") == "ok"
    assert fc.calls == ["model-b"]  # lower latency preferred


@pytest.mark.asyncio
async def test_deterministic_tie_break():
    p, fc = _make(_ok(), ["model-b", "model-a"])  # input order reversed
    assert await p.generate("q") == "ok"
    assert fc.calls == ["model-a"]  # alphabetical tie-break regardless of order


@pytest.mark.asyncio
async def test_one_request_per_candidate():
    p, fc = _make(_ok(), ["model-a", "model-b", "model-c"])
    await p.generate("q")
    assert fc.calls == ["model-a"]  # exactly one request when the first succeeds


@pytest.mark.asyncio
async def test_empty_pool_uses_fallback():
    p, fc = _make(_ok("fallback"), [], fallback="agnes-fallback")
    assert await p.generate("q") == "fallback"
    assert fc.calls == ["agnes-fallback"]


@pytest.mark.asyncio
async def test_all_pool_failed_then_fallback_used():
    def handler(m):
        if m == "agnes-fallback":
            return Resp(200, content="fallback-answer")
        return Resp(500)

    p, fc = _make(handler, ["model-a", "model-b"], fallback="agnes-fallback")
    assert await p.generate("q") == "fallback-answer"
    assert "model-a" in fc.calls and "model-b" in fc.calls
    assert "agnes-fallback" in fc.calls


@pytest.mark.asyncio
async def test_all_failed_no_fallback_raises_provider_error():
    from app.services.llm.providers.base import ProviderError

    p, fc = _make(lambda m: Resp(500), ["model-a"], fallback="")
    with pytest.raises(ProviderError):
        await p.generate("q")
