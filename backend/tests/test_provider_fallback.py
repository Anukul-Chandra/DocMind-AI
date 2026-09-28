"""Tests for provider fallback and missing API key handling."""

import pytest

from app.core.config import settings
from app.services.llm.factory import (
    build_provider_manager,
    build_openrouter_provider,
    build_gemini_provider,
    build_groq_provider,
    build_agnes_provider,
    build_opencode_provider,
)
from app.services.llm.provider_manager import ProviderManager, LLMUnavailableError


class StubProvider:
    """Minimal provider for testing."""

    def __init__(self, text="ok"):
        self._text = text

    @property
    def model(self):
        return "stub"

    async def generate(self, prompt, system_prompt=None, temperature=0.0, max_tokens=1000, images=None):
        return self._text


def test_openrouter_provider_returns_none_without_api_key(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    assert build_openrouter_provider() is None


def test_gemini_provider_returns_none_without_api_key(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")
    assert build_gemini_provider() is None


def test_groq_provider_returns_none_without_api_key(monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", "")
    assert build_groq_provider() is None


def test_agnes_provider_returns_none_without_api_key(monkeypatch):
    monkeypatch.setattr(settings, "agnes_api_key", "")
    assert build_agnes_provider() is None


def test_provider_manager_skips_missing_providers(monkeypatch):
    """When API keys are missing, providers should be skipped, not fail at request time."""
    monkeypatch.setattr(settings, "provider_priority", "openrouter,gemini,groq,agnes")
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "groq_api_key", "")
    monkeypatch.setattr(settings, "agnes_api_key", "")

    # All providers return None, so ProviderManager gets empty list
    pm = build_provider_manager()
    assert isinstance(pm, ProviderManager)
    assert len(pm._providers) == 0


def test_provider_manager_raises_clear_error_when_empty(monkeypatch):
    """ProviderManager should raise clear LLMUnavailableError when no providers configured."""
    monkeypatch.setattr(settings, "provider_priority", "openrouter,gemini,groq,agnes")
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "groq_api_key", "")
    monkeypatch.setattr(settings, "agnes_api_key", "")

    pm = build_provider_manager()

    import asyncio
    async def test():
        with pytest.raises(LLMUnavailableError) as exc_info:
            await pm.generate("test prompt")
        assert "No LLM providers configured" in str(exc_info.value)
        assert "API key" in str(exc_info.value)

    asyncio.run(test())


def test_provider_manager_uses_available_provider(monkeypatch):
    """When at least one provider has valid config, it should be used."""
    monkeypatch.setattr(settings, "provider_priority", "openrouter,gemini,groq")
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    monkeypatch.setattr(settings, "gemini_api_key", "valid-key")
    monkeypatch.setattr(settings, "groq_api_key", "")

    # Mock Gemini provider to return a stub
    import app.services.llm.factory as factory
    monkeypatch.setattr(factory, "build_gemini_provider", lambda: StubProvider("gemini-answer"))

    pm = build_provider_manager()
    assert len(pm._providers) == 1
    assert type(pm._providers[0]).__name__ == "StubProvider"

    import asyncio
    async def test():
        result = await pm.generate("test prompt")
        assert result.text == "gemini-answer"
        assert result.provider == "StubProvider"

    asyncio.run(test())


def test_provider_manager_fails_over_when_first_fails(monkeypatch):
    """When first provider fails with recoverable error, should try next provider."""
    monkeypatch.setattr(settings, "provider_priority", "openrouter,gemini,groq")
    monkeypatch.setattr(settings, "openrouter_api_key", "valid-key")
    monkeypatch.setattr(settings, "gemini_api_key", "valid-key")
    monkeypatch.setattr(settings, "groq_api_key", "valid-key")

    import app.services.llm.factory as factory
    from gateway.llm_gateway.contracts import ProviderError

    class FailingProvider:
        @property
        def model(self):
            return "failing"

        async def generate(self, *args, **kwargs):
            raise ProviderError("provider failed")

    monkeypatch.setattr(factory, "build_openrouter_provider", lambda: FailingProvider())
    monkeypatch.setattr(factory, "build_gemini_provider", lambda: StubProvider("gemini-answer"))
    monkeypatch.setattr(factory, "build_groq_provider", lambda: StubProvider("groq-answer"))

    pm = build_provider_manager()
    assert len(pm._providers) == 3

    import asyncio
    async def test():
        result = await pm.generate("test prompt")
        assert result.text == "gemini-answer"
        assert result.provider == "StubProvider"

    asyncio.run(test())


def test_opencode_provider_still_works_without_api_key(monkeypatch):
    """OpenCode doesn't require API key, should work if model discovery succeeds."""
    monkeypatch.setattr(settings, "provider_priority", "opencode")
    
    import app.services.llm.factory as factory
    monkeypatch.setattr(factory, "build_opencode_provider", lambda: StubProvider("opencode-answer"))

    pm = build_provider_manager()
    assert len(pm._providers) == 1

    import asyncio
    async def test():
        result = await pm.generate("test prompt")
        assert result.text == "opencode-answer"

    asyncio.run(test())


def test_unknown_provider_in_priority_logs_warning(monkeypatch, caplog):
    """Unknown provider in PROVIDER_PRIORITY should log warning and be skipped."""
    monkeypatch.setattr(settings, "provider_priority", "unknown,openrouter")
    monkeypatch.setattr(settings, "openrouter_api_key", "valid-key")

    import app.services.llm.factory as factory
    monkeypatch.setattr(factory, "build_openrouter_provider", lambda: StubProvider("or"))

    import logging
    caplog.set_level(logging.WARNING)
    pm = build_provider_manager()
    
    assert any("Unknown provider in PROVIDER_PRIORITY: unknown" in record.message for record in caplog.records)
    assert len(pm._providers) == 1