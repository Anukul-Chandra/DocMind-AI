"""Regression tests for the stale query-embedding bug in ChatService/QueryRouter.

These tests verify that the embedding used for semantic retrieval always
belongs to the CURRENT question and is never silently reused from a previous
question (or from another concurrent request). The embedding is request-local:
it is produced once per classification call and passed explicitly through the
retrieval path, rather than being read from shared mutable router state.

No live LLM / provider / FAISS / Postgres calls are made.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.llm import LLMResponse
from app.services.chat.chat_service import ChatService
from app.services.chat.query_router import QueryCategory, QueryRouter, RouteResult
from app.services.llm.prompt_builder import PromptBuilder
from app.services.rag.retrieval_evaluator import (
    RetrievalEvaluation,
    RetrievalEvaluator,
    RetrievalQuality,
)
from app.services.retrieval.base import Retriever


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeEmbeddingService:
    """Deterministic embedding service that tags each text with a unique id.

    The produced vector's first element is a stable per-text id, so tests can
    assert exactly which query text an embedding came from.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []
        self._seen: dict[str, list[float]] = {}
        self._counter = 0

    def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            self.calls.append(text)
            if text not in self._seen:
                self._seen[text] = [float(self._counter)]
                self._counter += 1
            out.append(list(self._seen[text]))
        return out

    def embedding_for(self, text: str) -> list[float]:
        return list(self._seen[text])


class FakeRelevanceScorer:
    """Returns a constant cosine similarity for the relevance gate."""

    def __init__(self, value: float = 1.0) -> None:
        self.value = value

    def __call__(self, question: str, owner_id: str, query_embedding) -> float:
        return self.value


class FakeLexicalScorer:
    """Returns a constant BM25 score for the lexical rescue branch."""

    def __init__(self, value: float = 1.0) -> None:
        self.value = value

    def __call__(self, question: str, owner_id: str) -> float:
        return self.value


class CaptureRetriever(Retriever):
    """Retriever that records the query_embedding passed to each retrieve()."""

    def __init__(self, by_query: dict[str, list[dict]] | None = None) -> None:
        self._by_query = by_query or {}
        self.calls: list[tuple[str, str, object]] = []

    def retrieve(self, query, k=5, workspace_id="default", owner_id="", query_embedding=None):
        self.calls.append((query, owner_id, query_embedding))
        return self._by_query.get(query, [])

    def is_eligible(self, document, workspace_id, owner_id=""):
        return True


class FakeRewriter:
    """Async fake of QueryRewriter that records the rewritten query."""

    def __init__(self, result: str) -> None:
        self.result = result
        self.calls: list[str] = []

    async def rewrite(self, query: str) -> str:
        self.calls.append(query)
        return self.result


class FakeEvaluator:
    """Constant-quality fake of RetrievalEvaluator."""

    def __init__(self, quality: RetrievalQuality, confidence: float = 0.5) -> None:
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
            best_rrf=0.0,
            best_lexical=0.0,
            best_rerank=0.0,
            context_count=len(chunks),
        )


def _doc_router(embedding_service):
    """A QueryRouter that routes arbitrary questions to DOCUMENT and embeds."""
    return QueryRouter(
        embedding_service=embedding_service,
        relevance_scorer=FakeRelevanceScorer(1.0),
        lexical_scorer=FakeLexicalScorer(1.0),
    )


def _make_service(retriever, embedding_service, evaluator=None, rewriter=None):
    router = QueryRouter(
        embedding_service=embedding_service,
        relevance_scorer=FakeRelevanceScorer(1.0),
        lexical_scorer=FakeLexicalScorer(1.0),
    )
    prompt_builder = MagicMock(spec=PromptBuilder)
    prompt_builder.build_prompt.return_value = MagicMock(text="prompt")
    prompt_builder.build_general_prompt.return_value = MagicMock(text="prompt")
    provider_manager = AsyncMock(spec=PromptBuilder)
    provider_manager.generate = AsyncMock(
        return_value=LLMResponse(text="answer", provider="p", model="m")
    )
    return ChatService(
        retriever=retriever,
        prompt_builder=prompt_builder,
        provider_manager=provider_manager,
        query_router=router,
        retrieval_evaluator=evaluator,
        query_rewriter=rewriter,
    )


# ---------------------------------------------------------------------------
# 1-3. Router produces a fresh, current-question embedding per call
# ---------------------------------------------------------------------------


def test_distinct_queries_get_distinct_embeddings():
    emb = FakeEmbeddingService()
    router = _doc_router(emb)

    route_a = router.classify_with_embedding("Question A about topic one")
    route_b = router.classify_with_embedding("Question B about topic two")

    assert route_a.category is QueryCategory.DOCUMENT
    assert route_b.category is QueryCategory.DOCUMENT
    # The two embeddings must differ and must belong to their own question.
    assert route_a.query_embedding != route_b.query_embedding
    assert route_a.query_embedding == emb.embedding_for("Question A about topic one")
    assert route_b.query_embedding == emb.embedding_for("Question B about topic two")


def test_query_b_does_not_reuse_query_a_embedding():
    emb = FakeEmbeddingService()
    router = _doc_router(emb)

    route_a = router.classify_with_embedding("first question")
    route_b = router.classify_with_embedding("second question")

    # route_b must carry the embedding of "second question", never "first".
    assert route_b.query_embedding == emb.embedding_for("second question")
    assert route_b.query_embedding != emb.embedding_for("first question")
    assert route_a.query_embedding != route_b.query_embedding


# ---------------------------------------------------------------------------
# 4. Two consecutive DOCUMENT queries use independent embeddings (via service)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_consecutive_document_queries_independent_embeddings():
    emb = FakeEmbeddingService()
    retriever = CaptureRetriever()
    service = _make_service(retriever, emb)

    await service.chat("summarize notes.txt please")
    await service.chat("summarize report.pdf now")

    assert len(retriever.calls) == 2
    q1, _, e1 = retriever.calls[0]
    q2, _, e2 = retriever.calls[1]
    assert q1 == "summarize notes.txt please"
    assert q2 == "summarize report.pdf now"
    # Each retrieval received the embedding of its OWN question.
    assert e1 == emb.embedding_for("summarize notes.txt please")
    assert e2 == emb.embedding_for("summarize report.pdf now")
    # And they are not the same (no reuse of the first embedding).
    assert e1 != e2


# ---------------------------------------------------------------------------
# 5. A GENERAL query cannot leave stale embedding state affecting next DOCUMENT
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_general_then_document_no_stale_state():
    emb = FakeEmbeddingService()
    retriever = CaptureRetriever()
    service = _make_service(retriever, emb)

    # "explain machine learning" is a GENERAL-ask verb; routes GENERAL.
    await service.chat("explain machine learning")
    # Now a DOCUMENT query.
    await service.chat("what does notes.txt say about the budget")

    assert len(retriever.calls) == 1  # only the DOCUMENT query retrieved
    q, _, e = retriever.calls[0]
    assert q == "what does notes.txt say about the budget"
    # The DOCUMENT retrieval got a fresh embedding for its own question,
    # not None and not anything left behind by the GENERAL query.
    assert e == emb.embedding_for("what does notes.txt say about the budget")
    assert e is not None


# ---------------------------------------------------------------------------
# 6. A METADATA query cannot leave stale embedding state affecting next DOCUMENT
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_metadata_then_document_no_stale_state():
    emb = FakeEmbeddingService()
    retriever = CaptureRetriever()
    service = _make_service(retriever, emb)

    await service.chat("how many documents did i upload")  # METADATA
    await service.chat("summarize notes.txt for me")  # DOCUMENT

    assert len(retriever.calls) == 1
    q, _, e = retriever.calls[0]
    assert q == "summarize notes.txt for me"
    assert e == emb.embedding_for("summarize notes.txt for me")
    assert e is not None


# ---------------------------------------------------------------------------
# 7. Corrective CRAG retrieval uses the rewritten query's embedding
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_crag_corrective_uses_rewritten_query_embedding():
    emb = FakeEmbeddingService()
    retriever = CaptureRetriever()
    evaluator = FakeEvaluator(RetrievalQuality.UNCERTAIN)
    rewriter = FakeRewriter("rewritten version of the question")
    # Build a CRAG-enabled service manually to wire the orchestrator.
    router = QueryRouter(
        embedding_service=emb,
        relevance_scorer=FakeRelevanceScorer(1.0),
        lexical_scorer=FakeLexicalScorer(1.0),
    )
    prompt_builder = MagicMock(spec=PromptBuilder)
    prompt_builder.build_prompt.return_value = MagicMock(text="prompt")
    provider_manager = AsyncMock()
    provider_manager.generate = AsyncMock(
        return_value=LLMResponse(text="answer", provider="p", model="m")
    )
    service = ChatService(
        retriever=retriever,
        prompt_builder=prompt_builder,
        provider_manager=provider_manager,
        query_router=router,
        retrieval_evaluator=evaluator,
        query_rewriter=rewriter,
    )

    await service.chat("original question about notes.txt")

    # Two retrieval passes: original then corrective rewrite.
    assert len(retriever.calls) == 2
    orig_q, _, orig_e = retriever.calls[0]
    corr_q, _, corr_e = retriever.calls[1]

    assert orig_q == "original question about notes.txt"
    # First pass uses the CURRENT (original) question's embedding.
    assert orig_e == emb.embedding_for("original question about notes.txt")

    assert corr_q == "rewritten version of the question"
    # Corrective pass must NOT reuse the original embedding; it passes None so
    # the retriever embeds the rewritten query freshly.
    assert corr_e is None


# ---------------------------------------------------------------------------
# 8. Multiple requests do not share embedding state (concurrency safety)
# ---------------------------------------------------------------------------


def test_embedding_is_request_local_no_shared_state():
    emb = FakeEmbeddingService()
    router = _doc_router(emb)

    # Simulate many distinct concurrent-style classifications on one shared
    # (singleton) router instance.
    results = [
        router.classify_with_embedding(f"question number {i}")
        for i in range(20)
    ]

    embeddings = [r.query_embedding for r in results]
    # All embeddings are distinct.
    assert len(set(map(tuple, embeddings))) == 20
    # Each embedding matches its own question and none leak across calls.
    for i, r in enumerate(results):
        assert r.query_embedding == emb.embedding_for(f"question number {i}")
    # No shared mutable embedding attribute remains on the router.
    assert not hasattr(router, "last_query_embedding")


@pytest.mark.asyncio
async def test_concurrent_users_do_not_share_embedding():
    emb = FakeEmbeddingService()
    retriever = CaptureRetriever()
    service_a = _make_service(retriever, emb)
    service_b = _make_service(retriever, emb)

    await service_a.chat("user A asks about notes.txt")
    await service_b.chat("user B asks about report.pdf")

    assert len(retriever.calls) == 2
    qa, _, ea = retriever.calls[0]
    qb, _, eb = retriever.calls[1]
    # A's retrieval used A's question embedding; B's used B's. No cross-leak.
    assert ea == emb.embedding_for("user A asks about notes.txt")
    assert eb == emb.embedding_for("user B asks about report.pdf")
    assert ea != eb


# ---------------------------------------------------------------------------
# 9. Existing retrieval behavior unchanged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_metadata_routes_without_retrieval():
    emb = FakeEmbeddingService()
    retriever = CaptureRetriever()
    service = _make_service(retriever, emb)

    resp = await service.chat("how many documents do i have")
    assert resp.category == "metadata"
    assert retriever.calls == []  # no semantic retrieval for METADATA


@pytest.mark.asyncio
async def test_general_routes_without_retrieval():
    emb = FakeEmbeddingService()
    retriever = CaptureRetriever()
    service = _make_service(retriever, emb)

    resp = await service.chat("explain machine learning")
    assert resp.category == "general"
    assert retriever.calls == []  # no semantic retrieval for GENERAL


@pytest.mark.asyncio
async def test_document_routes_with_retrieval_and_embedding():
    emb = FakeEmbeddingService()
    retriever = CaptureRetriever({"notes.txt": [{"chunk": 1}]})
    service = _make_service(retriever, emb)

    resp = await service.chat("summarize notes.txt")
    assert resp.category == "document"
    assert len(retriever.calls) == 1
    _, _, e = retriever.calls[0]
    assert e == emb.embedding_for("summarize notes.txt")
