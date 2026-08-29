"""Deterministic tests for the adaptive CRAG context-selection loop.

Covers Parts 3B and 3C.  All collaborators are fakes — no real retriever,
evaluator, rewriter, LLM, or provider calls are made.

Key behavior under test:
    - GOOD initial ............ keep initial, no rewrite.
    - BAD/UNCERTAIN initial ... one rewrite + one corrective retrieval, then
        select the best available evidence:
        * corrective GOOD ............. use corrective.
        * corrective UNCERTAIN ........ use the stronger of original /
                                         corrective (by eval signals).
        * corrective BAD + initial BAD  both attempts unusable -> empty final
                                        context (never fall back to weak
                                        original or corrective evidence).
    - Both attempts empty/insufficient -> empty final context.
    - Every TECHNICAL failure mode (rewrite failure, corrective retrieval
      failure, empty corrective retrieval, corrective evaluation failure)
      falls back safely to the original (or empty).
    - GENERAL / METADATA queries never enter CRAG.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import asyncio
import time

from app.models.llm import LLMResponse
from app.services.chat.chat_service import ChatService
from app.services.chat.query_router import QueryCategory, QueryRouter, RouteResult
from app.services.llm.prompt_builder import PromptBuilder
from app.services.llm.provider_manager import ProviderManager
from app.services.rag.crag import CragOrchestrator
from app.services.rag.retrieval_evaluator import (
    RetrievalEvaluation,
    RetrievalEvaluator,
    RetrievalQuality,
)
from app.services.retrieval.base import Retriever


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeRetriever:
    """Records retrieve() calls and returns per-query configured contexts."""

    def __init__(self, by_query: dict[str, list[dict]]):
        self._by_query = by_query
        self.calls: list[tuple] = []

    def retrieve(
        self,
        query: str,
        k: int = 5,
        workspace_id: str = "default",
        owner_id: str = "",
        query_embedding=None,
    ) -> list[dict]:
        self.calls.append((query, owner_id, query_embedding))
        return self._by_query.get(query, [])


class BoomRetriever(FakeRetriever):
    """Retriever that raises for a specific query (simulating a failure)."""

    def retrieve(self, query, **kwargs):
        self.calls.append((query, kwargs.get("owner_id", ""), kwargs.get("query_embedding")))
        if query == "boom":
            raise RuntimeError("retrieval down")
        return self._by_query.get(query, [])


class FakeRewriter:
    """Async fake of QueryRewriter that records the rewritten query."""

    def __init__(self, result: str):
        self.result = result
        self.calls: list[str] = []

    async def rewrite(self, query: str) -> str:
        self.calls.append(query)
        return self.result


class FailingRewriter:
    """Async fake that always raises, simulating a broken rewriter."""

    async def rewrite(self, query: str) -> str:
        raise RuntimeError("rewriter exploded")


class FakeEvaluator:
    """Constant-quality fake of RetrievalEvaluator (for simple scenarios)."""

    def __init__(self, quality: RetrievalQuality, confidence: float = 0.5):
        self.quality = quality
        self.confidence = confidence
        self.calls: list[tuple] = []

    def evaluate(self, query: str, chunks: list[dict]) -> RetrievalEvaluation:
        self.calls.append((query, chunks))
        return RetrievalEvaluation(
            quality=self.quality,
            confidence=self.confidence,
            reason="fake",
            best_semantic=0.0,
            best_rerank=0.0,
            best_lexical=0.0,
            best_rrf=0.0,
            context_count=len(chunks),
        )


class SequenceEvaluator:
    """Evaluator returning a configured (quality, confidence) per call."""

    def __init__(self, responses: list[tuple[RetrievalQuality, float]]):
        self._responses = list(responses)
        self._idx = 0
        self.calls: list[tuple] = []

    def evaluate(self, query: str, chunks: list[dict]) -> RetrievalEvaluation:
        self.calls.append((query, chunks))
        quality, confidence = self._responses[min(self._idx, len(self._responses) - 1)]
        self._idx += 1
        return RetrievalEvaluation(
            quality=quality,
            confidence=confidence,
            reason="fake",
            best_semantic=0.0,
            best_rerank=0.0,
            best_lexical=0.0,
            best_rrf=0.0,
            context_count=len(chunks),
        )


class BoomEvaluator:
    """Evaluator that succeeds for the initial call but raises on a query."""

    def __init__(self, quality: RetrievalQuality, confidence: float = 0.5, boom_on: str = "rewritten"):
        self.quality = quality
        self.confidence = confidence
        self.boom_on = boom_on
        self.calls: list[tuple] = []

    def evaluate(self, query: str, chunks: list[dict]) -> RetrievalEvaluation:
        self.calls.append((query, chunks))
        if query == self.boom_on:
            raise RuntimeError("evaluator boom")
        return RetrievalEvaluation(
            quality=self.quality,
            confidence=self.confidence,
            reason="fake",
            best_semantic=0.0,
            best_rerank=0.0,
            best_lexical=0.0,
            best_rrf=0.0,
            context_count=len(chunks),
        )


def _chunk(name: str) -> list[dict]:
    return [{"text": name, "filename": "f", "chunk_id": 0, "workspace_id": "w"}]


# ---------------------------------------------------------------------------
# Orchestrator-level tests
# ---------------------------------------------------------------------------

class TestInitialGood:
    @pytest.mark.asyncio
    async def test_good_no_rewrite_single_retrieval(self):
        initial = _chunk("initial")
        retriever = FakeRetriever({"orig": initial})
        evaluator = FakeEvaluator(RetrievalQuality.GOOD)

        orch = CragOrchestrator(retriever, evaluator, FakeRewriter("rewritten"))
        result = await orch.retrieve("orig", owner_id="u1")

        assert result == initial
        assert len(retriever.calls) == 1  # no corrective retrieval


class TestInitialBadCorrectiveGood:
    @pytest.mark.asyncio
    async def test_bad_then_good_uses_corrective(self):
        initial = _chunk("initial")
        corrected = _chunk("corrected")
        retriever = FakeRetriever({"orig": initial, "rewritten": corrected})
        evaluator = SequenceEvaluator(
            [(RetrievalQuality.BAD, 0.0), (RetrievalQuality.GOOD, 0.9)]
        )
        rewriter = FakeRewriter("rewritten")

        orch = CragOrchestrator(retriever, evaluator, rewriter)
        result = await orch.retrieve("orig", owner_id="u1")

        assert result == corrected
        assert rewriter.calls == ["orig"]
        assert len(retriever.calls) == 2


class TestInitialUncertainCorrectiveGood:
    @pytest.mark.asyncio
    async def test_uncertain_then_good_uses_corrective(self):
        initial = _chunk("initial")
        corrected = _chunk("corrected")
        retriever = FakeRetriever({"orig": initial, "rewritten": corrected})
        evaluator = SequenceEvaluator(
            [(RetrievalQuality.UNCERTAIN, 0.2), (RetrievalQuality.GOOD, 0.9)]
        )

        orch = CragOrchestrator(retriever, evaluator, FakeRewriter("rewritten"))
        result = await orch.retrieve("orig", owner_id="u1")

        assert result == corrected


class TestInitialBadCorrectiveBad:
    @pytest.mark.asyncio
    async def test_bad_then_bad_returns_empty(self):
        initial = _chunk("initial")
        corrected = _chunk("corrected")
        retriever = FakeRetriever({"orig": initial, "rewritten": corrected})
        evaluator = SequenceEvaluator(
            [(RetrievalQuality.BAD, 0.05), (RetrievalQuality.BAD, 0.05)]
        )

        orch = CragOrchestrator(retriever, evaluator, FakeRewriter("rewritten"))
        result = await orch.retrieve("orig", owner_id="u1")

        # Both attempts produced unusable evidence: never present either weak
        # result as trusted context. Final context must be empty even though
        # the original chunks were non-empty.
        assert result == []


class TestUncertainCorrectiveUncertain:
    @pytest.mark.asyncio
    async def test_uncertain_corrected_stronger_wins(self):
        initial = _chunk("initial")
        corrected = _chunk("corrected")
        retriever = FakeRetriever({"orig": initial, "rewritten": corrected})
        evaluator = SequenceEvaluator(
            [(RetrievalQuality.UNCERTAIN, 0.1), (RetrievalQuality.UNCERTAIN, 0.9)]
        )

        orch = CragOrchestrator(retriever, evaluator, FakeRewriter("rewritten"))
        result = await orch.retrieve("orig", owner_id="u1")

        assert result == corrected  # genuinely stronger corrective selected

    @pytest.mark.asyncio
    async def test_uncertain_original_stronger_wins(self):
        initial = _chunk("initial")
        corrected = _chunk("corrected")
        retriever = FakeRetriever({"orig": initial, "rewritten": corrected})
        evaluator = SequenceEvaluator(
            [(RetrievalQuality.UNCERTAIN, 0.9), (RetrievalQuality.UNCERTAIN, 0.1)]
        )

        orch = CragOrchestrator(retriever, evaluator, FakeRewriter("rewritten"))
        result = await orch.retrieve("orig", owner_id="u1")

        # Do NOT prefer the newer corrective merely because it exists.
        assert result == initial


class TestBothBadEmpty:
    @pytest.mark.asyncio
    async def test_both_attempts_empty_returns_empty(self):
        retriever = FakeRetriever({"orig": [], "rewritten": []})
        evaluator = SequenceEvaluator(
            [(RetrievalQuality.BAD, 0.0), (RetrievalQuality.BAD, 0.0)]
        )

        orch = CragOrchestrator(retriever, evaluator, FakeRewriter("rewritten"))
        result = await orch.retrieve("orig", owner_id="u1")

        assert result == []  # insufficient evidence -> empty, no fabrication


class TestBothBadFinalContext:
    """Intended behavior: Initial BAD + corrective BAD -> empty final context.

    This must hold even when the original (initial) contexts are non-empty, and
    even when the corrective contexts are non-empty. Neither weak result may be
    sent as trusted document context. Technical failures (rewriter/retrieval/
    evaluation exceptions, empty corrective) are a separate concern and keep
    their existing safe fallback to the original contexts.
    """

    @pytest.mark.asyncio
    async def test_initial_bad_corrective_bad_final_empty(self):
        initial = _chunk("initial")
        corrected = _chunk("corrected")
        retriever = FakeRetriever({"orig": initial, "rewritten": corrected})
        evaluator = SequenceEvaluator(
            [(RetrievalQuality.BAD, 0.05), (RetrievalQuality.BAD, 0.05)]
        )
        orch = CragOrchestrator(retriever, evaluator, FakeRewriter("rewritten"))
        result = await orch.retrieve("orig", owner_id="u1")
        assert result == []

    @pytest.mark.asyncio
    async def test_both_bad_nonempty_initial_and_corrective_empty(self):
        initial = _chunk("initial")
        corrected = _chunk("corrected")
        retriever = FakeRetriever({"orig": initial, "rewritten": corrected})
        evaluator = SequenceEvaluator(
            [(RetrievalQuality.BAD, 0.2), (RetrievalQuality.BAD, 0.1)]
        )
        orch = CragOrchestrator(retriever, evaluator, FakeRewriter("rewritten"))
        result = await orch.retrieve("orig", owner_id="u1")
        # Original non-empty chunk must NOT be returned as trusted context.
        assert result == []
        assert initial not in result

    @pytest.mark.asyncio
    async def test_both_bad_sources_empty_via_chat_service(self):
        retriever = FakeRetriever(
            {"orig": _chunk("initial"), "rewritten": _chunk("corrected")}
        )
        evaluator = SequenceEvaluator(
            [(RetrievalQuality.BAD, 0.05), (RetrievalQuality.BAD, 0.05)]
        )
        service = _make_service(retriever, evaluator, FakeRewriter("rewritten"))
        resp = await service.chat("orig", owner_id="u1")
        assert resp.sources == []

    @pytest.mark.asyncio
    async def test_original_question_reaches_prompt_builder_when_both_bad(self):
        initial = _chunk("initial")
        corrected = _chunk("corrected")
        retriever = FakeRetriever({"orig": initial, "rewritten": corrected})
        pb = MagicMock(spec=PromptBuilder)
        pb.build_prompt.return_value = MagicMock(text="prompt")
        service = ChatService(
            retriever=retriever,
            prompt_builder=pb,
            provider_manager=AsyncMock(
                generate=AsyncMock(
                    return_value=LLMResponse(text="answer", provider="p", model="m")
                )
            ),
            query_router=_router(QueryCategory.DOCUMENT),
            retrieval_evaluator=SequenceEvaluator(
                [(RetrievalQuality.BAD, 0.05), (RetrievalQuality.BAD, 0.05)]
            ),
            query_rewriter=FakeRewriter("rewritten"),
        )
        await service.chat("orig", owner_id="u1")
        call_args = pb.build_prompt.call_args
        assert call_args.args[0] == "orig"   # original question preserved
        assert call_args.args[1] == []       # empty contexts (insufficient)

    @pytest.mark.asyncio
    async def test_bad_then_good_uses_corrective(self):
        initial = _chunk("initial")
        corrected = _chunk("corrected")
        retriever = FakeRetriever({"orig": initial, "rewritten": corrected})
        evaluator = SequenceEvaluator(
            [(RetrievalQuality.BAD, 0.05), (RetrievalQuality.GOOD, 0.9)]
        )
        orch = CragOrchestrator(retriever, evaluator, FakeRewriter("rewritten"))
        result = await orch.retrieve("orig", owner_id="u1")
        assert result == corrected

    @pytest.mark.asyncio
    async def test_bad_then_uncertain_uses_stronger(self):
        initial = _chunk("initial")
        corrected = _chunk("corrected")
        retriever = FakeRetriever({"orig": initial, "rewritten": corrected})
        evaluator = SequenceEvaluator(
            [(RetrievalQuality.BAD, 0.05), (RetrievalQuality.UNCERTAIN, 0.9)]
        )
        orch = CragOrchestrator(retriever, evaluator, FakeRewriter("rewritten"))
        result = await orch.retrieve("orig", owner_id="u1")
        assert result == corrected

    @pytest.mark.asyncio
    async def test_corrective_retrieval_failure_preserves_fallback(self):
        initial = _chunk("initial")
        retriever = BoomRetriever({"orig": initial, "rewritten": _chunk("c")})
        orch = CragOrchestrator(
            retriever, FakeEvaluator(RetrievalQuality.UNCERTAIN), FakeRewriter("rewritten")
        )
        result = await orch.retrieve("orig", owner_id="u1")
        assert result == initial  # technical failure -> safe fallback

    @pytest.mark.asyncio
    async def test_empty_corrective_preserves_fallback(self):
        initial = _chunk("initial")
        retriever = FakeRetriever({"orig": initial, "rewritten": []})
        orch = CragOrchestrator(
            retriever, FakeEvaluator(RetrievalQuality.UNCERTAIN), FakeRewriter("rewritten")
        )
        result = await orch.retrieve("orig", owner_id="u1")
        assert result == initial  # empty corrective -> safe fallback

    @pytest.mark.asyncio
    async def test_rewriter_failure_preserves_fallback(self):
        initial = _chunk("initial")
        retriever = FakeRetriever({"orig": initial})
        orch = CragOrchestrator(
            retriever, FakeEvaluator(RetrievalQuality.BAD), FailingRewriter()
        )
        result = await orch.retrieve("orig", owner_id="u1")
        assert result == initial  # rewriter failure -> safe fallback

    @pytest.mark.asyncio
    async def test_no_extra_rewrite_or_retrieval_beyond_limits(self):
        initial = _chunk("initial")
        corrected = _chunk("corrected")
        retriever = FakeRetriever({"orig": initial, "rewritten": corrected})
        evaluator = SequenceEvaluator(
            [(RetrievalQuality.BAD, 0.05), (RetrievalQuality.BAD, 0.05)]
        )
        rewriter = FakeRewriter("rewritten")
        orch = CragOrchestrator(retriever, evaluator, rewriter)
        await orch.retrieve("orig", owner_id="u1")
        assert len(retriever.calls) == 2   # exactly two retrieval passes
        assert len(evaluator.calls) == 2   # exactly two evaluations
        assert len(rewriter.calls) == 1    # exactly one rewrite


class TestCorrectiveEmpty:
    @pytest.mark.asyncio
    async def test_corrective_empty_keeps_original(self):
        initial = _chunk("initial")
        retriever = FakeRetriever({"orig": initial, "rewritten": []})
        evaluator = FakeEvaluator(RetrievalQuality.UNCERTAIN)

        orch = CragOrchestrator(retriever, evaluator, FakeRewriter("rewritten"))
        result = await orch.retrieve("orig", owner_id="u1")

        assert result == initial


class TestCorrectiveEvaluatorFailure:
    @pytest.mark.asyncio
    async def test_evaluator_failure_falls_back_to_original(self):
        initial = _chunk("initial")
        corrected = _chunk("corrected")
        retriever = FakeRetriever({"orig": initial, "rewritten": corrected})
        evaluator = BoomEvaluator(RetrievalQuality.UNCERTAIN, boom_on="rewritten")

        orch = CragOrchestrator(retriever, evaluator, FakeRewriter("rewritten"))
        result = await orch.retrieve("orig", owner_id="u1")

        assert result == initial


class TestOriginalRetrievalFailure:
    @pytest.mark.asyncio
    async def test_empty_initial_and_corrective_is_safe(self):
        retriever = FakeRetriever({"orig": [], "rewritten": []})
        evaluator = SequenceEvaluator(
            [(RetrievalQuality.BAD, 0.0), (RetrievalQuality.BAD, 0.0)]
        )

        orch = CragOrchestrator(retriever, evaluator, FakeRewriter("rewritten"))
        result = await orch.retrieve("orig", owner_id="u1")

        # Safe behavior preserved: returns empty rather than crashing.
        assert result == []


class TestRewrittenQueryOnlyForRetrieval:
    @pytest.mark.asyncio
    async def test_rewritten_used_only_in_retrieval(self):
        initial = _chunk("initial")
        corrected = _chunk("corrected")
        retriever = FakeRetriever({"orig": initial, "rewritten": corrected})
        evaluator = FakeEvaluator(RetrievalQuality.UNCERTAIN)
        rewriter = FakeRewriter("rewritten")

        orch = CragOrchestrator(retriever, evaluator, rewriter)
        result = await orch.retrieve("orig", owner_id="u1")

        # Tie in confidence -> original kept, but the rewrite was still used
        # exclusively for the second retrieval pass.
        assert result == initial
        assert rewriter.calls == ["orig"]
        assert [c[0] for c in retriever.calls] == ["orig", "rewritten"]
        assert retriever.calls[1][2] is None  # fresh embedding for rewrite


class TestRewriterFailureFallsBack:
    @pytest.mark.asyncio
    async def test_rewriter_raises_returns_original(self):
        initial = _chunk("initial")
        retriever = FakeRetriever({"orig": initial})
        orch = CragOrchestrator(
            retriever, FakeEvaluator(RetrievalQuality.BAD), FailingRewriter()
        )
        result = await orch.retrieve("orig", owner_id="u1")
        assert result == initial
        assert len(retriever.calls) == 1

    @pytest.mark.asyncio
    async def test_rewriter_returns_original_uses_original(self):
        initial = _chunk("initial")
        retriever = FakeRetriever({"orig": initial})
        orch = CragOrchestrator(
            retriever, FakeEvaluator(RetrievalQuality.BAD), FakeRewriter("orig")
        )
        result = await orch.retrieve("orig", owner_id="u1")
        assert result == initial
        assert len(retriever.calls) == 1


class TestCorrectiveRetrievalFailureFallsBack:
    @pytest.mark.asyncio
    async def test_retrieval_exception_returns_original(self):
        initial = _chunk("initial")
        retriever = BoomRetriever({"orig": initial, "rewritten": _chunk("corrected")})
        orch = CragOrchestrator(
            retriever, FakeEvaluator(RetrievalQuality.UNCERTAIN), FakeRewriter("rewritten")
        )
        result = await orch.retrieve("orig", owner_id="u1")
        assert result == initial
        assert len(retriever.calls) == 2  # attempted both passes


class TestLimits:
    @pytest.mark.asyncio
    async def test_max_two_retrieval_passes(self):
        initial = _chunk("initial")
        corrected = _chunk("corrected")
        retriever = FakeRetriever({"orig": initial, "rewritten": corrected})
        evaluator = SequenceEvaluator(
            [(RetrievalQuality.BAD, 0.05), (RetrievalQuality.BAD, 0.05)]
        )
        orch = CragOrchestrator(retriever, evaluator, FakeRewriter("rewritten"))
        await orch.retrieve("orig", owner_id="u1")
        assert len(retriever.calls) == 2

    @pytest.mark.asyncio
    async def test_max_two_evaluations(self):
        initial = _chunk("initial")
        corrected = _chunk("corrected")
        retriever = FakeRetriever({"orig": initial, "rewritten": corrected})
        evaluator = SequenceEvaluator(
            [(RetrievalQuality.BAD, 0.05), (RetrievalQuality.BAD, 0.05)]
        )
        orch = CragOrchestrator(retriever, evaluator, FakeRewriter("rewritten"))
        await orch.retrieve("orig", owner_id="u1")
        assert len(evaluator.calls) == 2

    @pytest.mark.asyncio
    async def test_no_recursive_retry(self):
        initial = _chunk("initial")
        corrected = _chunk("corrected")
        retriever = FakeRetriever({"orig": initial, "rewritten": corrected})
        evaluator = SequenceEvaluator(
            [(RetrievalQuality.BAD, 0.05), (RetrievalQuality.BAD, 0.05)]
        )
        rewriter = FakeRewriter("rewritten")
        orch = CragOrchestrator(retriever, evaluator, rewriter)
        result = await orch.retrieve("orig", owner_id="u1")
        assert result == []  # both BAD -> empty, no further loop
        assert len(retriever.calls) == 2
        assert len(rewriter.calls) == 1  # exactly one rewrite


class TestDegenerateWithoutCollaborators:
    @pytest.mark.asyncio
    async def test_no_evaluator_single_retrieval(self):
        initial = _chunk("initial")
        retriever = FakeRetriever({"orig": initial})
        orch = CragOrchestrator(retriever, evaluator=None, rewriter=FakeRewriter("rewritten"))
        result = await orch.retrieve("orig", owner_id="u1")
        assert result == initial
        assert len(retriever.calls) == 1


# ---------------------------------------------------------------------------
# ChatService-level integration (sources reflect the final selected context)
# ---------------------------------------------------------------------------

def _router(category: QueryCategory) -> MagicMock:
    r = MagicMock(spec=QueryRouter)
    r.classify_with_embedding.return_value = RouteResult(
        category, [0.1, 0.2, 0.3]
    )
    return r


def _make_service(retriever, evaluator, rewriter, router_category=QueryCategory.DOCUMENT):
    return ChatService(
        retriever=retriever,
        prompt_builder=MagicMock(spec=PromptBuilder),
        provider_manager=AsyncMock(
            generate=AsyncMock(
                return_value=LLMResponse(text="answer", provider="p", model="m")
            )
        ),
        query_router=_router(router_category),
        retrieval_evaluator=evaluator,
        query_rewriter=rewriter,
    )


class TestChatServiceCragWiring:
    @pytest.mark.asyncio
    async def test_corrective_good_sources_match_corrective(self):
        initial = _chunk("initial")
        corrected = _chunk("corrected")
        retriever = FakeRetriever({"orig": initial, "rewritten": corrected})
        evaluator = SequenceEvaluator(
            [(RetrievalQuality.UNCERTAIN, 0.1), (RetrievalQuality.GOOD, 0.9)]
        )
        service = _make_service(retriever, evaluator, FakeRewriter("rewritten"))
        resp = await service.chat("orig", owner_id="u1")
        assert resp.sources == corrected

    @pytest.mark.asyncio
    async def test_initial_good_sources_match_initial(self):
        initial = _chunk("initial")
        retriever = FakeRetriever({"orig": initial})
        service = _make_service(
            retriever, FakeEvaluator(RetrievalQuality.GOOD), FakeRewriter("rewritten")
        )
        resp = await service.chat("orig", owner_id="u1")
        assert resp.sources == initial

    @pytest.mark.asyncio
    async def test_both_bad_sources_empty(self):
        retriever = FakeRetriever({"orig": [], "rewritten": []})
        evaluator = SequenceEvaluator(
            [(RetrievalQuality.BAD, 0.0), (RetrievalQuality.BAD, 0.0)]
        )
        service = _make_service(retriever, evaluator, FakeRewriter("rewritten"))
        resp = await service.chat("orig", owner_id="u1")
        assert resp.sources == []

    @pytest.mark.asyncio
    async def test_original_question_used_for_prompt_builder(self):
        initial = _chunk("initial")
        corrected = _chunk("corrected")
        retriever = FakeRetriever({"orig": initial, "rewritten": corrected})
        pb = MagicMock(spec=PromptBuilder)
        pb.build_prompt.return_value = MagicMock(text="prompt")
        service = ChatService(
            retriever=retriever,
            prompt_builder=pb,
            provider_manager=AsyncMock(
                generate=AsyncMock(
                    return_value=LLMResponse(text="answer", provider="p", model="m")
                )
            ),
            query_router=_router(QueryCategory.DOCUMENT),
            retrieval_evaluator=SequenceEvaluator(
                [(RetrievalQuality.UNCERTAIN, 0.1), (RetrievalQuality.GOOD, 0.9)]
            ),
            query_rewriter=FakeRewriter("rewritten"),
        )
        await service.chat("orig", owner_id="u1")
        call_args = pb.build_prompt.call_args
        assert call_args.args[0] == "orig"

    @pytest.mark.asyncio
    async def test_general_never_enters_crag(self):
        retriever = FakeRetriever({})
        service = _make_service(
            retriever,
            FakeEvaluator(RetrievalQuality.UNCERTAIN),
            FakeRewriter("rewritten"),
            router_category=QueryCategory.GENERAL,
        )
        await service.chat("hi", owner_id="u1")
        assert retriever.calls == []

    @pytest.mark.asyncio
    async def test_metadata_never_enters_crag(self):
        retriever = FakeRetriever({})
        service = _make_service(
            retriever,
            FakeEvaluator(RetrievalQuality.UNCERTAIN),
            FakeRewriter("rewritten"),
            router_category=QueryCategory.METADATA,
        )
        resp = await service.chat("list my docs", owner_id="u1")
        assert retriever.calls == []
        assert resp.category == "metadata"


# ---------------------------------------------------------------------------
# Rewrite deadline (hard outer latency ceiling)
# ---------------------------------------------------------------------------

class SlowRewriter:
    """Async fake that sleeps past any deadline and never returns on its own."""

    def __init__(self, hang: float):
        self.hang = hang
        self.calls: list[str] = []

    async def rewrite(self, query: str) -> str:
        self.calls.append(query)
        await asyncio.sleep(self.hang)
        return "rewritten"


class RotatingSlowRewriter:
    """Simulates an OpenCode-style internal rotation: many slow attempts."""

    def __init__(self, attempts: int, per_attempt: float):
        self._attempts = attempts
        self._per_attempt = per_attempt
        self.calls: list[str] = []

    async def rewrite(self, query: str) -> str:
        self.calls.append(query)
        for _ in range(self._attempts):
            await asyncio.sleep(self._per_attempt)
        return "rewritten"


class DelayedFailingRewriter:
    """Sleeps then raises, simulating a slow provider timeout/error."""

    def __init__(self, hang: float):
        self.hang = hang

    async def rewrite(self, query: str) -> str:
        await asyncio.sleep(self.hang)
        raise RuntimeError("provider timeout")


class TestRewriteDeadline:
    """The CRAG rewrite has a single hard outer deadline.

    On expiry the original contexts are preserved, corrective retrieval is
    skipped, and the chat request proceeds normally — exactly like an ordinary
    rewrite failure. The deadline is the ONLY outer boundary; it bounds any
    provider rotation/retry activity beneath it and leaves no orphan task.
    """

    @pytest.mark.asyncio
    async def test_fast_rewrite_within_deadline_runs_normally(self):
        initial = _chunk("initial")
        corrected = _chunk("corrected")
        retriever = FakeRetriever({"orig": initial, "rewritten": corrected})
        evaluator = SequenceEvaluator(
            [(RetrievalQuality.UNCERTAIN, 0.1), (RetrievalQuality.GOOD, 0.9)]
        )
        rewriter = FakeRewriter("rewritten")

        orch = CragOrchestrator(
            retriever, evaluator, rewriter, rewrite_timeout=2.0
        )
        result = await orch.retrieve("orig", owner_id="u1")

        assert result == corrected
        assert rewriter.calls == ["orig"]      # exactly one rewrite
        assert len(retriever.calls) == 2       # initial + corrective

    @pytest.mark.asyncio
    async def test_rewrite_timeout_preserves_original_no_corrective(self):
        initial = _chunk("initial")
        retriever = FakeRetriever({"orig": initial})
        orch = CragOrchestrator(
            retriever,
            FakeEvaluator(RetrievalQuality.UNCERTAIN),
            SlowRewriter(hang=5.0),
            rewrite_timeout=0.3,
        )
        result = await orch.retrieve("orig", owner_id="u1")

        assert result == initial               # original contexts preserved
        assert len(retriever.calls) == 1       # corrective retrieval skipped
        assert retriever.calls[0][0] == "orig" # original question unchanged

    @pytest.mark.asyncio
    async def test_rotation_cannot_exceed_total_deadline(self):
        initial = _chunk("initial")
        retriever = FakeRetriever({"orig": initial})
        # 5 attempts * 2s = 10s of internal rotation, far past the 0.5s ceiling.
        orch = CragOrchestrator(
            retriever,
            FakeEvaluator(RetrievalQuality.UNCERTAIN),
            RotatingSlowRewriter(attempts=5, per_attempt=2.0),
            rewrite_timeout=0.5,
        )
        start = time.monotonic()
        result = await orch.retrieve("orig", owner_id="u1")
        elapsed = time.monotonic() - start

        assert result == initial
        assert elapsed < 1.0   # hard outer boundary held
        assert len(retriever.calls) == 1

    @pytest.mark.asyncio
    async def test_rewriter_exception_falls_back_safely(self):
        initial = _chunk("initial")
        retriever = FakeRetriever({"orig": initial})
        orch = CragOrchestrator(
            retriever,
            FakeEvaluator(RetrievalQuality.BAD),
            FailingRewriter(),
            rewrite_timeout=1.0,
        )
        result = await orch.retrieve("orig", owner_id="u1")
        assert result == initial
        assert len(retriever.calls) == 1

    @pytest.mark.asyncio
    async def test_provider_timeout_falls_back_safely(self):
        initial = _chunk("initial")
        retriever = FakeRetriever({"orig": initial})
        orch = CragOrchestrator(
            retriever,
            FakeEvaluator(RetrievalQuality.UNCERTAIN),
            DelayedFailingRewriter(hang=1.0),
            rewrite_timeout=5.0,
        )
        result = await orch.retrieve("orig", owner_id="u1")
        assert result == initial
        assert len(retriever.calls) == 1

    @pytest.mark.asyncio
    async def test_initial_good_bypasses_rewrite_even_with_deadline(self):
        initial = _chunk("initial")
        retriever = FakeRetriever({"orig": initial})
        rewriter = FakeRewriter("rewritten")
        orch = CragOrchestrator(
            retriever, FakeEvaluator(RetrievalQuality.GOOD), rewriter,
            rewrite_timeout=0.3,
        )
        result = await orch.retrieve("orig", owner_id="u1")
        assert result == initial
        assert rewriter.calls == []            # no rewrite attempted
        assert len(retriever.calls) == 1

    @pytest.mark.asyncio
    async def test_both_bad_with_timed_out_rewrite_is_safe(self):
        # A timed-out rewrite behaves like any other rewrite failure: it returns
        # the original (BAD) contexts rather than hanging or crashing. The
        # both-BAD -> empty path still requires a *successful* rewrite, so it is
        # unchanged; this only confirms the timeout failure mode is safe.
        initial = _chunk("initial")
        retriever = FakeRetriever({"orig": initial, "rewritten": _chunk("corrected")})
        evaluator = SequenceEvaluator(
            [(RetrievalQuality.BAD, 0.05), (RetrievalQuality.BAD, 0.05)]
        )
        orch = CragOrchestrator(
            retriever, evaluator, SlowRewriter(hang=5.0), rewrite_timeout=0.3
        )
        result = await orch.retrieve("orig", owner_id="u1")
        assert result == initial
        assert len(retriever.calls) == 1

    @pytest.mark.asyncio
    async def test_chat_service_still_answers_when_rewrite_times_out(self):
        # Service-level proof: a timed-out rewrite must not break the chat turn.
        # Patch the configured deadline small so the test stays fast.
        initial = _chunk("initial")
        retriever = FakeRetriever({"orig": initial})
        pb = MagicMock(spec=PromptBuilder)
        pb.build_prompt.return_value = MagicMock(text="prompt")

        with patch(
            "app.core.config.settings.crag_rewrite_timeout_seconds", 0.3
        ):
            service = ChatService(
                retriever=retriever,
                prompt_builder=pb,
                provider_manager=AsyncMock(
                    generate=AsyncMock(
                        return_value=LLMResponse(text="answer", provider="p", model="m")
                    )
                ),
                query_router=_router(QueryCategory.DOCUMENT),
                retrieval_evaluator=FakeEvaluator(RetrievalQuality.UNCERTAIN),
                query_rewriter=SlowRewriter(hang=5.0),
            )
            resp = await service.chat("orig", owner_id="u1")

        assert resp.text == "answer"          # normal answer generation proceeded
        assert len(retriever.calls) == 1      # no corrective retrieval attempted
        assert retriever.calls[0][0] == "orig"  # original question used for retrieval
        # Original question (not the rewrite) drives the prompt.
        assert pb.build_prompt.call_args.args[0] == "orig"
