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
        * corrective BAD .............. never use bad corrective; prefer the
                                        original if non-empty, else empty.
    - Both attempts empty/insufficient -> empty final context.
    - Every failure mode falls back safely to the original (or empty).
    - GENERAL / METADATA queries never enter CRAG.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.llm import LLMResponse
from app.services.chat.chat_service import ChatService
from app.services.chat.query_router import QueryCategory, QueryRouter
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
    async def test_bad_then_bad_keeps_original(self):
        initial = _chunk("initial")
        corrected = _chunk("corrected")
        retriever = FakeRetriever({"orig": initial, "rewritten": corrected})
        evaluator = SequenceEvaluator(
            [(RetrievalQuality.BAD, 0.05), (RetrievalQuality.BAD, 0.05)]
        )

        orch = CragOrchestrator(retriever, evaluator, FakeRewriter("rewritten"))
        result = await orch.retrieve("orig", owner_id="u1")

        # Do NOT use the bad corrective contexts; keep the original (usable).
        assert result == initial


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
        assert result == initial  # corrected BAD -> original, no further loop
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
    r.classify.return_value = category
    r.last_query_embedding = [0.1, 0.2, 0.3]
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
