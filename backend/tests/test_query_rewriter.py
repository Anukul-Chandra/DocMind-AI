"""Deterministic tests for QueryRewriter.

All tests use a fake ProviderManager — no real LLM calls are made.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.llm import LLMResponse
from app.services.llm.provider_manager import (
    LLMUnavailableError,
    ProviderManager,
)
from app.services.rag.query_rewriter import QueryRewriter


def _fake_provider_manager(return_text: str = "education, university, degree"):
    """Create a fake ProviderManager whose generate() returns *return_text*."""
    pm = MagicMock(spec=ProviderManager)
    pm.generate = AsyncMock(
        return_value=LLMResponse(text=return_text, provider="fake", model="test")
    )
    return pm


def _failing_provider_manager(error_msg: str = "provider down"):
    """Create a fake ProviderManager whose generate() always raises."""
    pm = MagicMock(spec=ProviderManager)
    pm.generate = AsyncMock(side_effect=LLMUnavailableError(error_msg))
    return pm


class TestNormalRewrite:
    """Provider returns valid rewritten text."""

    @pytest.mark.asyncio
    async def test_rewritten_query_returned(self):
        pm = _fake_provider_manager("education, university, degree")
        rw = QueryRewriter(pm)
        result = await rw.rewrite("what did I study?")
        assert result == "education, university, degree"

    @pytest.mark.asyncio
    async def test_preserves_names_and_entities(self):
        pm = _fake_provider_manager("John Smith employment history, work experience")
        rw = QueryRewriter(pm)
        result = await rw.rewrite("tell me about John Smith's career")
        assert "John Smith" in result

    @pytest.mark.asyncio
    async def test_whitespace_normalised(self):
        pm = _fake_provider_manager("  education   university   degree  ")
        rw = QueryRewriter(pm)
        result = await rw.rewrite("what did I study?")
        assert result == "education university degree"
        assert "  " not in result

    @pytest.mark.asyncio
    async def test_single_provider_call(self):
        pm = _fake_provider_manager("rewritten query")
        rw = QueryRewriter(pm)
        await rw.rewrite("question")
        assert pm.generate.call_count == 1


class TestProviderFailure:
    """Provider raises an exception — original query returned."""

    @pytest.mark.asyncio
    async def test_unavailable_error_returns_original(self):
        pm = _failing_provider_manager("All providers failed")
        rw = QueryRewriter(pm)
        result = await rw.rewrite("what did I study?")
        assert result == "what did I study?"

    @pytest.mark.asyncio
    async def test_generic_exception_returns_original(self):
        pm = MagicMock(spec=ProviderManager)
        pm.generate = AsyncMock(side_effect=RuntimeError("unexpected"))
        rw = QueryRewriter(pm)
        result = await rw.rewrite("question")
        assert result == "question"

    @pytest.mark.asyncio
    async def test_provider_failure_no_crash(self):
        pm = _failing_provider_manager()
        rw = QueryRewriter(pm)
        result = await rw.rewrite("anything")
        assert isinstance(result, str)


class TestEmptyResponse:
    """Provider returns empty or whitespace-only text."""

    @pytest.mark.asyncio
    async def test_empty_string_returns_original(self):
        pm = _fake_provider_manager("")
        rw = QueryRewriter(pm)
        result = await rw.rewrite("what did I study?")
        assert result == "what did I study?"

    @pytest.mark.asyncio
    async def test_whitespace_only_returns_original(self):
        pm = _fake_provider_manager("   \n\t  ")
        rw = QueryRewriter(pm)
        result = await rw.rewrite("question")
        assert result == "question"

    @pytest.mark.asyncio
    async def test_none_like_empty_returns_original(self):
        pm = _fake_provider_manager("  ")
        rw = QueryRewriter(pm)
        result = await rw.rewrite("question")
        assert result == "question"


class TestMaxLength:
    """Provider returns text exceeding the hard cap."""

    @pytest.mark.asyncio
    async def test_overlong_returns_original(self):
        long_text = "word " * 100  # 500 chars
        pm = _fake_provider_manager(long_text)
        rw = QueryRewriter(pm, max_output_length=200)
        result = await rw.rewrite("question")
        assert result == "question"

    @pytest.mark.asyncio
    async def test_exactly_at_limit_is_accepted(self):
        text = "a" * 200
        pm = _fake_provider_manager(text)
        rw = QueryRewriter(pm, max_output_length=200)
        result = await rw.rewrite("question")
        assert result == text

    @pytest.mark.asyncio
    async def test_one_over_limit_rejected(self):
        text = "a" * 201
        pm = _fake_provider_manager(text)
        rw = QueryRewriter(pm, max_output_length=200)
        result = await rw.rewrite("question")
        assert result == "question"


class TestNoAnswerGeneration:
    """The rewriter never produces an answer — only a search query."""

    @pytest.mark.asyncio
    async def test_no_answer_keywords(self):
        pm = _fake_provider_manager("education university degree academic")
        rw = QueryRewriter(pm)
        result = await rw.rewrite("what did I study?")
        answer_indicators = [
            "according to", "based on the", "the document says",
            "you studied", "your degree", "the answer is",
        ]
        for indicator in answer_indicators:
            assert indicator.lower() not in result.lower()


class TestInputHandling:
    """Edge cases for the input query."""

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty(self):
        pm = _fake_provider_manager("anything")
        rw = QueryRewriter(pm)
        result = await rw.rewrite("")
        assert result == ""

    @pytest.mark.asyncio
    async def test_whitespace_input_returns_whitespace(self):
        pm = _fake_provider_manager("anything")
        rw = QueryRewriter(pm)
        result = await rw.rewrite("   ")
        assert result == "   "

    @pytest.mark.asyncio
    async def test_provider_not_called_on_empty_input(self):
        pm = _fake_provider_manager("anything")
        rw = QueryRewriter(pm)
        await rw.rewrite("")
        pm.generate.assert_not_called()


class TestSystemPrompt:
    """Verify the correct system prompt is passed to the provider."""

    @pytest.mark.asyncio
    async def test_system_prompt_contains_rewrite_instruction(self):
        pm = _fake_provider_manager("rewritten")
        rw = QueryRewriter(pm)
        await rw.rewrite("question")
        _, kwargs = pm.generate.call_args
        assert "retrieval query optimizer" in kwargs["system_prompt"].lower()
        assert "do not answer" in kwargs["system_prompt"].lower()

    @pytest.mark.asyncio
    async def test_temperature_is_zero(self):
        pm = _fake_provider_manager("rewritten")
        rw = QueryRewriter(pm)
        await rw.rewrite("question")
        _, kwargs = pm.generate.call_args
        assert kwargs["temperature"] == 0.0

    @pytest.mark.asyncio
    async def test_max_tokens_is_small(self):
        pm = _fake_provider_manager("rewritten")
        rw = QueryRewriter(pm)
        await rw.rewrite("question")
        _, kwargs = pm.generate.call_args
        assert kwargs["max_tokens"] <= 60
