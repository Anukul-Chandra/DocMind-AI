"""Tests for RetrievalEvaluator integration into ChatService.

Proves that:
- DOCUMENT queries call the evaluator
- GENERAL and METADATA queries bypass the evaluator
- All three quality levels (GOOD/UNCERTAIN/BAD) produce normal answer flow
- response.sources remain intact
- Existing routing behavior is preserved
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.llm import LLMResponse
from app.services.chat.chat_service import ChatService
from app.services.chat.query_router import QueryCategory, QueryRouter
from app.services.llm.prompt_builder import PromptBuilder
from app.services.llm.provider_manager import ProviderManager
from app.services.rag.retrieval_evaluator import (
    RetrievalEvaluation,
    RetrievalEvaluator,
    RetrievalQuality,
)
from app.services.retrieval.base import Retriever


def _make_retriever(contexts=None):
    r = MagicMock(spec=Retriever)
    r.retrieve.return_value = contexts or []
    return r


def _make_provider(text="answer", provider="openrouter", model="m"):
    pm = MagicMock(spec=ProviderManager)
    pm.generate = AsyncMock(
        return_value=LLMResponse(text=text, provider=provider, model=model)
    )
    return pm


def _make_router(category: QueryCategory):
    r = MagicMock(spec=QueryRouter)
    r.classify.return_value = category
    r.last_query_embedding = [0.1, 0.2, 0.3]
    return r


def _make_evaluator(quality=RetrievalQuality.GOOD):
    ev = MagicMock(spec=RetrievalEvaluator)
    ev.evaluate.return_value = RetrievalEvaluation(
        quality=quality,
        confidence=0.8,
        reason="test",
        best_semantic=0.5,
        best_rerank=0.6,
        best_lexical=0.3,
        best_rrf=0.01,
        context_count=3,
    )
    return ev


class TestEvaluatorCalledForDocumentQueries:
    """Evaluator is invoked on DOCUMENT-category queries."""

    @pytest.mark.asyncio
    async def test_evaluator_called(self):
        contexts = [{"text": "chunk", "semantic_score": 0.5}]
        ev = _make_evaluator()
        service = ChatService(
            retriever=_make_retriever(contexts),
            prompt_builder=MagicMock(spec=PromptBuilder),
            provider_manager=_make_provider(),
            query_router=_make_router(QueryCategory.DOCUMENT),
            retrieval_evaluator=ev,
        )
        await service.chat("What is X?")
        ev.evaluate.assert_called_once_with("What is X?", contexts)

    @pytest.mark.asyncio
    async def test_evaluator_receives_correct_chunks(self):
        contexts = [
            {"text": "a", "semantic_score": 0.9},
            {"text": "b", "semantic_score": 0.1},
        ]
        ev = _make_evaluator()
        service = ChatService(
            retriever=_make_retriever(contexts),
            prompt_builder=MagicMock(spec=PromptBuilder),
            provider_manager=_make_provider(),
            query_router=_make_router(QueryCategory.DOCUMENT),
            retrieval_evaluator=ev,
        )
        await service.chat("question")
        call_args = ev.evaluate.call_args
        assert call_args.args[0] == "question"
        assert call_args.args[1] is contexts


class TestEvaluatorBypassedForNonDocumentQueries:
    """Evaluator is NOT called on GENERAL or METADATA queries."""

    @pytest.mark.asyncio
    async def test_general_bypasses_evaluator(self):
        ev = _make_evaluator()
        service = ChatService(
            retriever=_make_retriever(),
            prompt_builder=MagicMock(spec=PromptBuilder),
            provider_manager=_make_provider(),
            query_router=_make_router(QueryCategory.GENERAL),
            retrieval_evaluator=ev,
        )
        await service.chat("Hello!")
        ev.evaluate.assert_not_called()

    @pytest.mark.asyncio
    async def test_metadata_bypasses_evaluator(self):
        ev = _make_evaluator()
        service = ChatService(
            retriever=_make_retriever(),
            prompt_builder=MagicMock(spec=PromptBuilder),
            provider_manager=_make_provider(),
            query_router=_make_router(QueryCategory.METADATA),
            retrieval_evaluator=ev,
        )
        resp = await service.chat("What docs do I have?")
        ev.evaluate.assert_not_called()
        assert resp.category == "metadata"


class TestEvaluatorOptional:
    """Service works fine when no evaluator is provided."""

    @pytest.mark.asyncio
    async def test_none_evaluator_no_crash(self):
        service = ChatService(
            retriever=_make_retriever([{"text": "x"}]),
            prompt_builder=MagicMock(spec=PromptBuilder),
            provider_manager=_make_provider(),
            query_router=_make_router(QueryCategory.DOCUMENT),
            retrieval_evaluator=None,
        )
        resp = await service.chat("What is X?")
        assert resp.text == "answer"


class TestAllQualityLevelsNormalFlow:
    """All three quality levels produce the same normal answer flow."""

    @pytest.mark.asyncio
    async def test_good_continues_normally(self):
        contexts = [{"text": "chunk", "semantic_score": 0.9}]
        ev = _make_evaluator(RetrievalQuality.GOOD)
        pb = MagicMock(spec=PromptBuilder)
        pb.build_prompt.return_value = MagicMock(text="prompt")
        pm = _make_provider(text="good answer")
        service = ChatService(
            retriever=_make_retriever(contexts),
            prompt_builder=pb,
            provider_manager=pm,
            query_router=_make_router(QueryCategory.DOCUMENT),
            retrieval_evaluator=ev,
        )
        resp = await service.chat("question")
        assert resp.text == "good answer"
        pb.build_prompt.assert_called_once()

    @pytest.mark.asyncio
    async def test_uncertain_continues_normally(self):
        contexts = [{"text": "chunk", "semantic_score": 0.2}]
        ev = _make_evaluator(RetrievalQuality.UNCERTAIN)
        pb = MagicMock(spec=PromptBuilder)
        pb.build_prompt.return_value = MagicMock(text="prompt")
        pm = _make_provider(text="uncertain answer")
        service = ChatService(
            retriever=_make_retriever(contexts),
            prompt_builder=pb,
            provider_manager=pm,
            query_router=_make_router(QueryCategory.DOCUMENT),
            retrieval_evaluator=ev,
        )
        resp = await service.chat("question")
        assert resp.text == "uncertain answer"

    @pytest.mark.asyncio
    async def test_bad_continues_normally(self):
        contexts = [{"text": "chunk", "semantic_score": 0.0}]
        ev = _make_evaluator(RetrievalQuality.BAD)
        pb = MagicMock(spec=PromptBuilder)
        pb.build_prompt.return_value = MagicMock(text="prompt")
        pm = _make_provider(text="bad answer")
        service = ChatService(
            retriever=_make_retriever(contexts),
            prompt_builder=pb,
            provider_manager=pm,
            query_router=_make_router(QueryCategory.DOCUMENT),
            retrieval_evaluator=ev,
        )
        resp = await service.chat("question")
        assert resp.text == "bad answer"


class TestSourcesIntact:
    """response.sources always contains the retrieved contexts."""

    @pytest.mark.asyncio
    async def test_sources_after_good(self):
        contexts = [
            {"text": "a", "semantic_score": 0.9},
            {"text": "b", "semantic_score": 0.8},
        ]
        service = ChatService(
            retriever=_make_retriever(contexts),
            prompt_builder=MagicMock(spec=PromptBuilder),
            provider_manager=_make_provider(),
            query_router=_make_router(QueryCategory.DOCUMENT),
            retrieval_evaluator=_make_evaluator(RetrievalQuality.GOOD),
        )
        resp = await service.chat("question")
        assert resp.sources is contexts

    @pytest.mark.asyncio
    async def test_sources_after_bad(self):
        contexts = [{"text": "x", "semantic_score": 0.0}]
        service = ChatService(
            retriever=_make_retriever(contexts),
            prompt_builder=MagicMock(spec=PromptBuilder),
            provider_manager=_make_provider(),
            query_router=_make_router(QueryCategory.DOCUMENT),
            retrieval_evaluator=_make_evaluator(RetrievalQuality.BAD),
        )
        resp = await service.chat("question")
        assert resp.sources is contexts

    @pytest.mark.asyncio
    async def test_category_set_after_evaluator(self):
        contexts = [{"text": "x"}]
        service = ChatService(
            retriever=_make_retriever(contexts),
            prompt_builder=MagicMock(spec=PromptBuilder),
            provider_manager=_make_provider(),
            query_router=_make_router(QueryCategory.DOCUMENT),
            retrieval_evaluator=_make_evaluator(),
        )
        resp = await service.chat("question")
        assert resp.category == QueryCategory.DOCUMENT.value


class TestRoutingPreserved:
    """Existing routing behavior is unchanged."""

    @pytest.mark.asyncio
    async def test_metadata_returns_immediately(self):
        service = ChatService(
            retriever=_make_retriever(),
            prompt_builder=MagicMock(spec=PromptBuilder),
            provider_manager=_make_provider(),
            query_router=_make_router(QueryCategory.METADATA),
            retrieval_evaluator=_make_evaluator(),
        )
        resp = await service.chat("list my docs")
        assert resp.category == "metadata"
        assert "document" in resp.text.lower()

    @pytest.mark.asyncio
    async def test_general_no_retrieval(self):
        retriever = _make_retriever()
        service = ChatService(
            retriever=retriever,
            prompt_builder=MagicMock(spec=PromptBuilder),
            provider_manager=_make_provider(),
            query_router=_make_router(QueryCategory.GENERAL),
            retrieval_evaluator=_make_evaluator(),
        )
        await service.chat("Hi!")
        retriever.retrieve.assert_not_called()


class TestNoDebugInfoExposed:
    """Evaluator details are not exposed in the response."""

    @pytest.mark.asyncio
    async def test_no_evaluator_fields_in_response(self):
        contexts = [{"text": "chunk", "semantic_score": 0.9}]
        ev = _make_evaluator(RetrievalQuality.BAD)
        service = ChatService(
            retriever=_make_retriever(contexts),
            prompt_builder=MagicMock(spec=PromptBuilder),
            provider_manager=_make_provider(text="normal answer"),
            query_router=_make_router(QueryCategory.DOCUMENT),
            retrieval_evaluator=ev,
        )
        resp = await service.chat("question")
        assert not hasattr(resp, "retrieval_quality")
        assert not hasattr(resp, "evaluation")
        assert "BAD" not in resp.text
        assert "UNCERTAIN" not in resp.text
