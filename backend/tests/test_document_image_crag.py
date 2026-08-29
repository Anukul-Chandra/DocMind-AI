"""Regression tests: DOCUMENT + IMAGE through the CRAG retrieval path.

These verify that an image attached to a DOCUMENT question is preserved
end-to-end while the CRAG machinery operates purely on the text query:

- The image is forwarded to the final provider request in every CRAG outcome
  (GOOD, BAD->GOOD, BOTH-BAD, corrective-failure fallback).
- The original user question is never replaced by the rewritten retrieval query
  when CRAG corrects.
- The QueryRewriter is invoked only with the text query; image bytes/content are
  never sent to it.
- A GENERAL + image request still uses the plain multimodal path and never
  enters document CRAG simply because an image is present.

No real providers / retrievers / LLMs are used.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.llm import LLMResponse
from app.services.chat.chat_service import ChatService
from app.services.chat.query_router import QueryCategory, QueryRouter, RouteResult
from app.services.llm.prompt_builder import PromptBuilder
from app.services.llm.provider_manager import ProviderManager
from app.services.rag.query_rewriter import QueryRewriter
from app.services.rag.retrieval_evaluator import (
    RetrievalEvaluation,
    RetrievalEvaluator,
    RetrievalQuality,
)
from app.services.retrieval.base import Retriever


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _ByQueryRetriever(Retriever):
    """Deterministic retriever keyed by query text."""

    def __init__(self, by_query: dict[str, list[dict]], boom_on: str | None = None) -> None:
        self._by_query = by_query
        self._boom_on = boom_on
        self.calls: list[tuple] = []

    def retrieve(self, query, k=5, workspace_id="default", owner_id="", query_embedding=None):
        self.calls.append((query, owner_id, query_embedding))
        if self._boom_on is not None and query == self._boom_on:
            raise RuntimeError("retrieval down")
        return self._by_query.get(query, [])

    def is_eligible(self, document, workspace_id, owner_id=""):
        return True


class _SequenceEvaluator(RetrievalEvaluator):
    """Returns the configured quality for each successive evaluate() call."""

    def __init__(self, qualities: list[RetrievalQuality]) -> None:
        self._qualities = list(qualities)
        self.calls: list[tuple] = []

    def evaluate(self, query: str, chunks: list[dict]) -> RetrievalEvaluation:
        self.calls.append((query, chunks))
        quality = self._qualities.pop(0) if self._qualities else RetrievalQuality.BAD
        return RetrievalEvaluation(
            quality=quality,
            confidence=0.8,
            reason="sequence",
            best_semantic=0.0,
            best_rerank=0.0,
            best_lexical=0.0,
            best_rrf=0.0,
            context_count=len(chunks),
        )


def _router(category: QueryCategory) -> MagicMock:
    r = MagicMock(spec=QueryRouter)
    r.classify_with_embedding.return_value = RouteResult(category, [0.1, 0.2, 0.3])
    return r


def _image(mime: str = "image/png") -> dict:
    return {"mime": mime, "data": "BASE64DATA"}


def _make_service(retriever, evaluator, rewriter, router_category=QueryCategory.DOCUMENT):
    """Build a ChatService whose provider captures (text, images)."""
    pb = MagicMock(spec=PromptBuilder)
    pb.build_prompt.return_value = MagicMock(text="rag prompt")
    pb.build_general_prompt.return_value = MagicMock(text="general prompt")

    captured: dict = {}

    async def fake_generate(prompt, images=None, **kwargs):
        captured["text"] = prompt
        captured["images"] = images
        return LLMResponse(text="answer", provider="p", model="m")

    pm = AsyncMock(spec=ProviderManager)
    pm.generate = fake_generate

    service = ChatService(
        retriever=retriever,
        prompt_builder=pb,
        provider_manager=pm,
        query_router=_router(router_category),
        retrieval_evaluator=evaluator,
        query_rewriter=rewriter,
    )
    return service, captured, pb


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------


class TestDocumentImageCrag:
    """DOCUMENT + image must keep the image through every CRAG outcome."""

    @pytest.mark.asyncio
    async def test_image_preserved_on_initial_good(self):
        initial = [{"text": "doc ctx", "filename": "a.pdf", "chunk_id": 0}]
        retriever = _ByQueryRetriever({"q": initial})
        evaluator = _SequenceEvaluator([RetrievalQuality.GOOD])
        rewriter = MagicMock(spec=QueryRewriter)
        rewriter.rewrite = AsyncMock(return_value="rewritten q")

        service, captured, pb = _make_service(retriever, evaluator, rewriter)
        imgs = [_image()]
        await service.chat("q", owner_id="u1", images=imgs)

        # Image forwarded to provider, exactly once, no duplication.
        assert captured["images"] == imgs
        assert len(captured["images"]) == 1
        # Original question drives the prompt; no rewrite on GOOD.
        assert pb.build_prompt.call_args.args[0] == "q"
        assert rewriter.rewrite.await_count == 0

    @pytest.mark.asyncio
    async def test_image_preserved_on_bad_to_good_correction(self):
        initial = [{"text": "weak ctx", "filename": "a.pdf", "chunk_id": 0}]
        corrected = [{"text": "strong ctx", "filename": "a.pdf", "chunk_id": 1}]
        retriever = _ByQueryRetriever({"q": initial, "rewritten q": corrected})
        evaluator = _SequenceEvaluator([RetrievalQuality.BAD, RetrievalQuality.GOOD])
        rewriter = MagicMock(spec=QueryRewriter)
        rewriter.rewrite = AsyncMock(return_value="rewritten q")

        service, captured, pb = _make_service(retriever, evaluator, rewriter)
        imgs = [_image()]
        await service.chat("q", owner_id="u1", images=imgs)

        # Image still forwarded (no loss during the corrective rewrite).
        assert captured["images"] == imgs
        assert len(captured["images"]) == 1
        # Rewrite happened and was used ONLY for retrieval.
        assert rewriter.rewrite.await_count == 1
        assert rewriter.rewrite.call_args.args[0] == "q"
        assert retriever.calls[-1][0] == "rewritten q"
        # Final prompt uses the ORIGINAL question, not the rewrite.
        assert pb.build_prompt.call_args.args[0] == "q"

    @pytest.mark.asyncio
    async def test_image_preserved_on_both_bad(self):
        initial = [{"text": "weak ctx", "filename": "a.pdf", "chunk_id": 0}]
        corrected = [{"text": "also weak", "filename": "a.pdf", "chunk_id": 1}]
        retriever = _ByQueryRetriever({"q": initial, "rewritten q": corrected})
        evaluator = _SequenceEvaluator([RetrievalQuality.BAD, RetrievalQuality.BAD])
        rewriter = MagicMock(spec=QueryRewriter)
        rewriter.rewrite = AsyncMock(return_value="rewritten q")

        service, captured, pb = _make_service(retriever, evaluator, rewriter)
        imgs = [_image()]
        resp = await service.chat("q", owner_id="u1", images=imgs)

        # Image preserved even though final context is empty.
        assert captured["images"] == imgs
        assert len(captured["images"]) == 1
        # No trusted context, but image + original question still delivered.
        assert resp.sources == []
        assert pb.build_prompt.call_args.args[0] == "q"

    @pytest.mark.asyncio
    async def test_image_preserved_on_corrective_retrieval_failure(self):
        initial = [{"text": "weak ctx", "filename": "a.pdf", "chunk_id": 0}]
        # Corrective retrieval raises; safe fallback to original contexts.
        retriever = _ByQueryRetriever({"q": initial}, boom_on="rewritten q")
        evaluator = _SequenceEvaluator([RetrievalQuality.BAD])
        rewriter = MagicMock(spec=QueryRewriter)
        rewriter.rewrite = AsyncMock(return_value="rewritten q")

        service, captured, pb = _make_service(retriever, evaluator, rewriter)
        imgs = [_image()]
        await service.chat("q", owner_id="u1", images=imgs)

        # Image preserved across the technical corrective failure.
        assert captured["images"] == imgs
        assert len(captured["images"]) == 1
        # Original contexts retained by the safe fallback.
        assert pb.build_prompt.call_args.args[0] == "q"

    @pytest.mark.asyncio
    async def test_image_not_sent_to_query_rewriter(self):
        initial = [{"text": "weak ctx", "filename": "a.pdf", "chunk_id": 0}]
        corrected = [{"text": "strong ctx", "filename": "a.pdf", "chunk_id": 1}]
        retriever = _ByQueryRetriever({"q": initial, "rewritten q": corrected})
        evaluator = _SequenceEvaluator([RetrievalQuality.BAD, RetrievalQuality.GOOD])
        rewriter = MagicMock(spec=QueryRewriter)
        rewriter.rewrite = AsyncMock(return_value="rewritten q")

        service, captured, _ = _make_service(retriever, evaluator, rewriter)
        imgs = [_image()]
        await service.chat("q", owner_id="u1", images=imgs)

        # The rewriter received only the text query -- never image content.
        assert rewriter.rewrite.await_count == 1
        call = rewriter.rewrite.call_args
        args = list(call.args) + list(call.kwargs.values())
        for arg in args:
            assert arg == "q"  # only the question string, no image dict
            assert not (isinstance(arg, dict) and ("data" in arg or "mime" in arg))


class TestGeneralImageBypassesCrag:
    """IMAGE + GENERAL must use the plain multimodal path, not document CRAG."""

    @pytest.mark.asyncio
    async def test_general_image_bypasses_crag(self):
        retriever = _ByQueryRetriever({})
        evaluator = _SequenceEvaluator([RetrievalQuality.GOOD])
        rewriter = MagicMock(spec=QueryRewriter)
        rewriter.rewrite = AsyncMock(return_value="rewritten q")

        service, captured, pb = _make_service(
            retriever, evaluator, rewriter, router_category=QueryCategory.GENERAL
        )
        imgs = [_image()]
        await service.chat("describe this picture", owner_id="u1", images=imgs)

        # No document retrieval / CRAG occurred.
        assert retriever.calls == []
        assert rewriter.rewrite.await_count == 0
        # Plain multimodal path: image still forwarded, general prompt used.
        assert captured["images"] == imgs
        assert pb.build_general_prompt.call_args.args[0] == "describe this picture"
