"""Deterministic tests for the corrective-retrieval loop (CRAG Part 3B).

All collaborators are fakes — no real retriever, evaluator, rewriter, LLM,
or provider calls are made.

Covered:
    1. GOOD initial retrieval -> no rewrite, one retrieval.
    2. UNCERTAIN initial retrieval -> rewrite + second retrieval.
    3. BAD initial retrieval -> rewrite + second retrieval.
    4. Rewritten query is used ONLY for retrieval.
    5. Original user question is still used for the final PromptBuilder.
    6. Corrected contexts become final sources when useful.
    7. Empty corrected retrieval falls back to original contexts.
    8. Rewriter failure falls back safely.
    9. Corrective retrieval failure falls back safely.
   10. Maximum two retrieval passes.
   11. No recursive retry.
   12. GENERAL query never enters CRAG.
   13. METADATA query never enters CRAG.
   14. Existing RAG/evaluator behavior is preserved (run separately).
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
    """Synchronous fake of RetrievalEvaluator that returns a fixed quality."""

    def __init__(self, quality: RetrievalQuality):
        self.quality = quality
        self.calls: list[tuple] = []

    def evaluate(self, query: str, chunks: list[dict]) -> RetrievalEvaluation:
        self.calls.append((query, chunks))
        return RetrievalEvaluation(
            quality=self.quality,
            confidence=0.5,
            reason="fake",
            best_semantic=0.0,
            best_rerank=0.0,
            best_lexical=0.0,
            best_rrf=0.0,
            context_count=len(chunks),
        )


def _ctx(name: str) -> list[dict]:
    return [{"text": name, "filename": "f", "chunk_id": 0, "workspace_id": "w"}]


# ---------------------------------------------------------------------------
# Orchestrator-level tests
# ---------------------------------------------------------------------------

class TestGoodInitialRetrieval:
    @pytest.mark.asyncio
    async def test_good_no_rewrite_single_retrieval(self):
        initial = _ctx("initial")
        retriever = FakeRetriever({"orig": initial})
        evaluator = FakeEvaluator(RetrievalQuality.GOOD)
        rewriter = FakeRewriter("rewritten")

        orch = CragOrchestrator(retriever, evaluator, rewriter)
        result = await orch.retrieve("orig", owner_id="u1")

        assert result == initial
        assert rewriter.calls == []  # no rewrite
        assert len(retriever.calls) == 1
        assert retriever.calls[0][0] == "orig"


class TestUncertainInitialRetrieval:
    @pytest.mark.asyncio
    async def test_uncertain_rewrites_and_retrieves_again(self):
        initial = _ctx("initial")
        corrected = _ctx("corrected")
        retriever = FakeRetriever({"orig": initial, "rewritten": corrected})
        evaluator = FakeEvaluator(RetrievalQuality.UNCERTAIN)
        rewriter = FakeRewriter("rewritten")

        orch = CragOrchestrator(retriever, evaluator, rewriter)
        result = await orch.retrieve("orig", owner_id="u1")

        assert result == corrected
        assert rewriter.calls == ["orig"]  # rewritten from original
        assert len(retriever.calls) == 2
        assert retriever.calls[0][0] == "orig"
        # 2nd retrieval uses the rewritten query and recomputes its embedding
        assert retriever.calls[1][0] == "rewritten"
        assert retriever.calls[1][2] is None


class TestBadInitialRetrieval:
    @pytest.mark.asyncio
    async def test_bad_rewrites_and_retrieves_again(self):
        initial = _ctx("initial")
        corrected = _ctx("corrected")
        retriever = FakeRetriever({"orig": initial, "rewritten": corrected})
        evaluator = FakeEvaluator(RetrievalQuality.BAD)
        rewriter = FakeRewriter("rewritten")

        orch = CragOrchestrator(retriever, evaluator, rewriter)
        result = await orch.retrieve("orig", owner_id="u1")

        assert result == corrected
        assert rewriter.calls == ["orig"]
        assert len(retriever.calls) == 2


class TestRewrittenQueryOnlyForRetrieval:
    @pytest.mark.asyncio
    async def test_rewritten_used_only_in_retrieval(self):
        initial = _ctx("initial")
        corrected = _ctx("corrected")
        retriever = FakeRetriever({"orig": initial, "rewritten": corrected})
        evaluator = FakeEvaluator(RetrievalQuality.UNCERTAIN)
        rewriter = FakeRewriter("rewritten")

        orch = CragOrchestrator(retriever, evaluator, rewriter)
        await orch.retrieve("orig", owner_id="u1")

        # The rewriter only ever sees the ORIGINAL query, never a rewritten one.
        assert rewriter.calls == ["orig"]
        # Both retrievals use the supplied queries (orig then rewritten);
        # the orchestrator holds no separate "answer query".
        assert [c[0] for c in retriever.calls] == ["orig", "rewritten"]


class TestEmptyCorrectedFallsBack:
    @pytest.mark.asyncio
    async def test_empty_corrected_returns_original(self):
        initial = _ctx("initial")
        retriever = FakeRetriever({"orig": initial, "rewritten": []})
        evaluator = FakeEvaluator(RetrievalQuality.UNCERTAIN)
        rewriter = FakeRewriter("rewritten")

        orch = CragOrchestrator(retriever, evaluator, rewriter)
        result = await orch.retrieve("orig", owner_id="u1")

        assert result == initial  # fell back
        assert len(retriever.calls) == 2


class TestRewriterFailureFallsBack:
    @pytest.mark.asyncio
    async def test_rewriter_raises_returns_original(self):
        initial = _ctx("initial")
        retriever = FakeRetriever({"orig": initial})
        evaluator = FakeEvaluator(RetrievalQuality.BAD)
        rewriter = FailingRewriter()

        orch = CragOrchestrator(retriever, evaluator, rewriter)
        result = await orch.retrieve("orig", owner_id="u1")

        assert result == initial
        assert len(retriever.calls) == 1  # no corrective retrieval

    @pytest.mark.asyncio
    async def test_rewriter_returns_original_uses_original(self):
        initial = _ctx("initial")
        retriever = FakeRetriever({"orig": initial})
        evaluator = FakeEvaluator(RetrievalQuality.BAD)
        rewriter = FakeRewriter("orig")  # rewriter failed -> echoes original

        orch = CragOrchestrator(retriever, evaluator, rewriter)
        result = await orch.retrieve("orig", owner_id="u1")

        assert result == initial
        assert rewriter.calls == ["orig"]
        assert len(retriever.calls) == 1


class TestCorrectiveRetrievalFailureFallsBack:
    @pytest.mark.asyncio
    async def test_retrieval_exception_returns_original(self):
        initial = _ctx("initial")

        class BoomRetriever(FakeRetriever):
            def retrieve(self, query, **kwargs):
                # Record the attempt, then fail (as a real retriever might).
                self.calls.append((query, kwargs.get("owner_id", ""), kwargs.get("query_embedding")))
                if query == "rewritten":
                    raise RuntimeError("retrieval down")
                return self._by_query.get(query, [])

        retriever = BoomRetriever({"orig": initial})
        evaluator = FakeEvaluator(RetrievalQuality.UNCERTAIN)
        rewriter = FakeRewriter("rewritten")

        orch = CragOrchestrator(retriever, evaluator, rewriter)
        result = await orch.retrieve("orig", owner_id="u1")

        assert result == initial
        assert len(retriever.calls) == 2


class TestLimits:
    @pytest.mark.asyncio
    async def test_max_two_retrieval_passes(self):
        initial = _ctx("initial")
        corrected = _ctx("corrected")
        retriever = FakeRetriever({"orig": initial, "rewritten": corrected})
        evaluator = FakeEvaluator(RetrievalQuality.BAD)
        rewriter = FakeRewriter("rewritten")

        orch = CragOrchestrator(retriever, evaluator, rewriter)
        await orch.retrieve("orig", owner_id="u1")

        assert len(retriever.calls) == 2  # never a 3rd pass

    @pytest.mark.asyncio
    async def test_max_two_evaluations(self):
        initial = _ctx("initial")
        corrected = _ctx("corrected")
        retriever = FakeRetriever({"orig": initial, "rewritten": corrected})
        evaluator = FakeEvaluator(RetrievalQuality.BAD)
        rewriter = FakeRewriter("rewritten")

        orch = CragOrchestrator(retriever, evaluator, rewriter)
        await orch.retrieve("orig", owner_id="u1")

        assert len(evaluator.calls) == 2  # initial + corrected, never more

    @pytest.mark.asyncio
    async def test_no_recursive_retry(self):
        # Even if the corrected evaluation is also BAD, there is no third pass.
        initial = _ctx("initial")
        corrected = _ctx("corrected")
        retriever = FakeRetriever({"orig": initial, "rewritten": corrected})
        evaluator = FakeEvaluator(RetrievalQuality.BAD)
        rewriter = FakeRewriter("rewritten")

        orch = CragOrchestrator(retriever, evaluator, rewriter)
        result = await orch.retrieve("orig", owner_id="u1")

        assert result == corrected  # corrected used, but no further loop
        assert len(retriever.calls) == 2
        assert len(rewriter.calls) == 1


class TestDegenerateWithoutCollaborators:
    @pytest.mark.asyncio
    async def test_no_evaluator_single_retrieval(self):
        initial = _ctx("initial")
        retriever = FakeRetriever({"orig": initial})
        rewriter = FakeRewriter("rewritten")

        orch = CragOrchestrator(retriever, evaluator=None, rewriter=rewriter)
        result = await orch.retrieve("orig", owner_id="u1")

        assert result == initial
        assert rewriter.calls == []  # never invoked
        assert len(retriever.calls) == 1


# ---------------------------------------------------------------------------
# ChatService-level integration (ensures rewrite is wired but prompt is original)
# ---------------------------------------------------------------------------

def _chat_service_with_crag(
    retriever,
    evaluator_quality: RetrievalQuality,
    rewriter_result: str | None = "rewritten",
    router_category: QueryCategory = QueryCategory.DOCUMENT,
):
    rewriter = FakeRewriter(rewriter_result) if rewriter_result is not None else FailingRewriter()
    service = ChatService(
        retriever=retriever,
        prompt_builder=MagicMock(spec=PromptBuilder),
        provider_manager=AsyncMock(
            generate=AsyncMock(
                return_value=LLMResponse(text="answer", provider="p", model="m")
            )
        ),
        query_router=_router(router_category),
        retrieval_evaluator=FakeEvaluator(evaluator_quality),
        query_rewriter=rewriter,
    )
    return service, rewriter


def _router(category: QueryCategory):
    r = MagicMock(spec=QueryRouter)
    r.classify.return_value = category
    r.last_query_embedding = [0.1, 0.2, 0.3]
    return r


class TestChatServiceCragWiring:
    @pytest.mark.asyncio
    async def test_corrected_contexts_become_final_sources(self):
        initial = _ctx("initial")
        corrected = _ctx("corrected")
        retriever = FakeRetriever({"orig": initial, "rewritten": corrected})

        service, rewriter = _chat_service_with_crag(
            retriever, RetrievalQuality.UNCERTAIN, rewriter_result="rewritten"
        )
        resp = await service.chat("orig", owner_id="u1")

        assert resp.sources == corrected
        assert rewriter.calls == ["orig"]

    @pytest.mark.asyncio
    async def test_original_question_used_for_prompt_builder(self):
        initial = _ctx("initial")
        corrected = _ctx("corrected")
        retriever = FakeRetriever({"orig": initial, "rewritten": corrected})

        pb = MagicMock(spec=PromptBuilder)
        pb.build_prompt.return_value = MagicMock(text="prompt")
        rewriter = FakeRewriter("rewritten")
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
            query_rewriter=rewriter,
        )
        await service.chat("orig", owner_id="u1")

        # PromptBuilder receives the ORIGINAL question, not the rewritten one.
        call_args = pb.build_prompt.call_args
        assert call_args.args[0] == "orig"
        assert call_args.args[0] != "rewritten"

    @pytest.mark.asyncio
    async def test_empty_corrected_falls_back_in_chat(self):
        initial = _ctx("initial")
        retriever = FakeRetriever({"orig": initial, "rewritten": []})

        service, _ = _chat_service_with_crag(
            retriever, RetrievalQuality.UNCERTAIN, rewriter_result="rewritten"
        )
        resp = await service.chat("orig", owner_id="u1")

        assert resp.sources == initial

    @pytest.mark.asyncio
    async def test_general_never_enters_crag(self):
        retriever = FakeRetriever({})
        service, rewriter = _chat_service_with_crag(
            retriever, RetrievalQuality.UNCERTAIN, router_category=QueryCategory.GENERAL
        )
        await service.chat("hi", owner_id="u1")

        assert retriever.calls == []
        assert rewriter.calls == []

    @pytest.mark.asyncio
    async def test_metadata_never_enters_crag(self):
        retriever = FakeRetriever({})
        service, rewriter = _chat_service_with_crag(
            retriever, RetrievalQuality.UNCERTAIN, router_category=QueryCategory.METADATA
        )
        resp = await service.chat("list my docs", owner_id="u1")

        assert retriever.calls == []
        assert rewriter.calls == []
        assert resp.category == "metadata"
