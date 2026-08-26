"""Tests for retrieval score propagation through the pipeline.

Verifies that semantic_score, lexical_score, rrf_score, and rerank_score
are attached to chunk dicts without breaking existing fields, ranking order,
ownership filtering, or the existing prompt-builder contract.
"""

from unittest.mock import MagicMock

import numpy as np
import pytest

from app.services.retrieval.bm25_retriever import BM25Retriever
from app.services.retrieval.hybrid_retriever import HybridRetriever
from app.services.retrieval.reranker import SemanticReranker
from app.services.vectorstore.retriever import SemanticRetriever


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chunk(
    workspace_id: str = "default",
    filename: str = "doc.txt",
    chunk_id: int = 0,
    document_id: str = "d1",
    owner_id: str = "u1",
    text: str = "sample text",
) -> dict:
    return {
        "id": 1,
        "workspace_id": workspace_id,
        "filename": filename,
        "chunk_id": chunk_id,
        "document_id": document_id,
        "owner_id": owner_id,
        "text": text,
    }


def _make_mock_registry():
    mock = MagicMock()
    mock.is_deleted.return_value = False
    return mock


# ---------------------------------------------------------------------------
# 1. SemanticRetriever — semantic_score is attached
# ---------------------------------------------------------------------------

class TestSemanticRetrieverScorePropagation:
    def test_semantic_score_attached(self):
        mock_embedding_service = MagicMock()
        mock_vector_store = MagicMock()
        mock_metadata_store = MagicMock()
        mock_document_registry = _make_mock_registry()

        embedding = [0.1] * 384
        mock_embedding_service.generate_embeddings.return_value = [embedding]

        mock_vector_store.search.return_value = (np.array([[0.5]]), np.array([[0]]))
        mock_vector_store.ntotal = 1
        mock_vector_store.get_embedding.return_value = [0.1] * 384

        chunk = _make_chunk()
        mock_metadata_store.get_document.return_value = chunk

        retriever = SemanticRetriever(
            mock_embedding_service, mock_vector_store, mock_metadata_store, mock_document_registry
        )
        results = retriever.retrieve("test query", k=5, workspace_id="default", owner_id="u1")

        assert len(results) == 1
        assert "semantic_score" in results[0]
        assert isinstance(results[0]["semantic_score"], float)
        assert -1.0 <= results[0]["semantic_score"] <= 1.0

    def test_original_fields_preserved(self):
        mock_embedding_service = MagicMock()
        mock_vector_store = MagicMock()
        mock_metadata_store = MagicMock()
        mock_document_registry = _make_mock_registry()

        embedding = [0.1] * 384
        mock_embedding_service.generate_embeddings.return_value = [embedding]
        mock_vector_store.search.return_value = (np.array([[0.5]]), np.array([[0]]))
        mock_vector_store.ntotal = 1
        mock_vector_store.get_embedding.return_value = [0.1] * 384

        chunk = _make_chunk(filename="resume.pdf", chunk_id=3, text="hello world")
        mock_metadata_store.get_document.return_value = chunk

        retriever = SemanticRetriever(
            mock_embedding_service, mock_vector_store, mock_metadata_store, mock_document_registry
        )
        results = retriever.retrieve("test", k=5, workspace_id="default", owner_id="u1")

        doc = results[0]
        assert doc["filename"] == "resume.pdf"
        assert doc["chunk_id"] == 3
        assert doc["text"] == "hello world"
        assert doc["workspace_id"] == "default"
        assert doc["owner_id"] == "u1"

    def test_ranking_order_unchanged(self):
        mock_embedding_service = MagicMock()
        mock_vector_store = MagicMock()
        mock_metadata_store = MagicMock()
        mock_document_registry = _make_mock_registry()

        embedding = [0.1] * 384
        mock_embedding_service.generate_embeddings.return_value = [embedding]

        chunk_a = _make_chunk(filename="a.txt", chunk_id=0, text="alpha")
        chunk_b = _make_chunk(filename="b.txt", chunk_id=1, text="beta")

        mock_vector_store.search.return_value = (np.array([[0.1, 0.9]]), np.array([[0, 1]]))
        mock_vector_store.ntotal = 2
        mock_vector_store.get_embedding.return_value = [0.1] * 384

        mock_metadata_store.get_document.side_effect = [chunk_a, chunk_b]

        retriever = SemanticRetriever(
            mock_embedding_service, mock_vector_store, mock_metadata_store, mock_document_registry
        )
        results = retriever.retrieve("test", k=5, workspace_id="default", owner_id="u1")

        assert len(results) == 2
        assert results[0]["filename"] == "a.txt"
        assert results[1]["filename"] == "b.txt"

    def test_reuses_precomputed_embedding(self):
        mock_embedding_service = MagicMock()
        mock_vector_store = MagicMock()
        mock_metadata_store = MagicMock()
        mock_document_registry = _make_mock_registry()

        embedding = [0.2] * 384
        mock_vector_store.search.return_value = (np.array([[0.3]]), np.array([[0]]))
        mock_vector_store.ntotal = 1
        mock_vector_store.get_embedding.return_value = [0.2] * 384
        mock_metadata_store.get_document.return_value = _make_chunk()

        retriever = SemanticRetriever(
            mock_embedding_service, mock_vector_store, mock_metadata_store, mock_document_registry
        )
        retriever.retrieve("test", k=5, workspace_id="default", owner_id="u1", query_embedding=embedding)

        mock_embedding_service.generate_embeddings.assert_not_called()


# ---------------------------------------------------------------------------
# 2. BM25Retriever — lexical_score is attached
# ---------------------------------------------------------------------------

class TestBM25RetrieverScorePropagation:
    def _make_retriever(self, chunks):
        mock_metadata_store = MagicMock()
        mock_document_registry = _make_mock_registry()

        mock_metadata_store.get_all_documents.return_value = chunks
        mock_metadata_store.get_document.side_effect = lambda i: chunks[i]

        retriever = BM25Retriever(mock_metadata_store, mock_document_registry)
        return retriever

    def test_lexical_score_attached(self):
        chunks = [
            _make_chunk(text="machine learning algorithms"),
            _make_chunk(text="natural language processing"),
        ]
        retriever = self._make_retriever(chunks)
        results = retriever.retrieve("machine learning", k=5, workspace_id="default", owner_id="u1")

        assert len(results) > 0
        for doc in results:
            assert "lexical_score" in doc
            assert isinstance(doc["lexical_score"], float)
            assert doc["lexical_score"] > 0.0

    def test_original_fields_preserved(self):
        chunks = [
            _make_chunk(filename="paper.pdf", chunk_id=5, text="deep learning"),
        ]
        retriever = self._make_retriever(chunks)
        results = retriever.retrieve("deep learning", k=5, workspace_id="default", owner_id="u1")

        assert len(results) == 1
        doc = results[0]
        assert doc["filename"] == "paper.pdf"
        assert doc["chunk_id"] == 5
        assert doc["text"] == "deep learning"
        assert doc["workspace_id"] == "default"

    def test_ranking_order_by_score(self):
        chunks = [
            _make_chunk(chunk_id=0, text="the cat sat on the mat"),
            _make_chunk(chunk_id=1, text="machine learning deep learning neural networks"),
            _make_chunk(chunk_id=2, text="a brief history of time"),
        ]
        retriever = self._make_retriever(chunks)
        results = retriever.retrieve("machine learning", k=5, workspace_id="default", owner_id="u1")

        assert len(results) > 0
        scores = [doc["lexical_score"] for doc in results]
        assert scores == sorted(scores, reverse=True)

    def test_empty_query_returns_nothing(self):
        chunks = [_make_chunk(text="some text")]
        retriever = self._make_retriever(chunks)
        results = retriever.retrieve("", k=5, workspace_id="default", owner_id="u1")
        assert results == []


# ---------------------------------------------------------------------------
# 3. HybridRetriever._fuse() — rrf_score attached, scores merged on dedup
# ---------------------------------------------------------------------------

class TestHybridRetrieverFuse:
    def test_rrf_score_attached(self):
        hybrid = HybridRetriever(
            semantic_retriever=MagicMock(),
            bm25_retriever=MagicMock(),
        )
        semantic = [_make_chunk(chunk_id=0, text="alpha")]
        keyword = [_make_chunk(chunk_id=1, text="beta")]

        fused = hybrid._fuse(semantic, keyword)

        assert len(fused) == 2
        for chunk in fused:
            assert "rrf_score" in chunk
            assert isinstance(chunk["rrf_score"], float)
            assert chunk["rrf_score"] > 0.0

    def test_rrf_scores_ranked_best_first(self):
        hybrid = HybridRetriever(
            semantic_retriever=MagicMock(),
            bm25_retriever=MagicMock(),
        )
        semantic = [
            _make_chunk(chunk_id=0, text="first"),
            _make_chunk(chunk_id=1, text="second"),
            _make_chunk(chunk_id=2, text="third"),
        ]
        keyword = [_make_chunk(chunk_id=3, text="fourth")]

        fused = hybrid._fuse(semantic, keyword)

        scores = [c["rrf_score"] for c in fused]
        assert scores == sorted(scores, reverse=True)

    def test_dedup_merges_semantic_and_lexical_scores(self):
        hybrid = HybridRetriever(
            semantic_retriever=MagicMock(),
            bm25_retriever=MagicMock(),
        )
        chunk_s = _make_chunk(chunk_id=0, text="shared")
        chunk_s["semantic_score"] = 0.85
        chunk_k = _make_chunk(chunk_id=0, text="shared")
        chunk_k["lexical_score"] = 3.2

        fused = hybrid._fuse([chunk_s], [chunk_k])

        assert len(fused) == 1
        assert fused[0]["semantic_score"] == 0.85
        assert fused[0]["lexical_score"] == 3.2
        assert "rrf_score" in fused[0]

    def test_dedup_does_not_overwrite_existing_score(self):
        hybrid = HybridRetriever(
            semantic_retriever=MagicMock(),
            bm25_retriever=MagicMock(),
        )
        chunk_s = _make_chunk(chunk_id=0, text="shared")
        chunk_s["semantic_score"] = 0.90
        chunk_k = _make_chunk(chunk_id=0, text="shared")
        chunk_k["semantic_score"] = 0.50
        chunk_k["lexical_score"] = 2.0

        fused = hybrid._fuse([chunk_s], [chunk_k])

        assert len(fused) == 1
        assert fused[0]["semantic_score"] == 0.90

    def test_original_fields_preserved_after_fuse(self):
        hybrid = HybridRetriever(
            semantic_retriever=MagicMock(),
            bm25_retriever=MagicMock(),
        )
        chunk = _make_chunk(filename="report.pdf", chunk_id=7, text="analysis")
        fused = hybrid._fuse([chunk], [])

        assert len(fused) == 1
        assert fused[0]["filename"] == "report.pdf"
        assert fused[0]["chunk_id"] == 7
        assert fused[0]["text"] == "analysis"

    def test_semantic_only_chunk_has_no_lexical_score(self):
        hybrid = HybridRetriever(
            semantic_retriever=MagicMock(),
            bm25_retriever=MagicMock(),
        )
        chunk = _make_chunk(chunk_id=0, text="unique to semantic")
        chunk["semantic_score"] = 0.7

        fused = hybrid._fuse([chunk], [])

        assert len(fused) == 1
        assert fused[0]["semantic_score"] == 0.7
        assert "lexical_score" not in fused[0]

    def test_bm25_only_chunk_has_no_semantic_score(self):
        hybrid = HybridRetriever(
            semantic_retriever=MagicMock(),
            bm25_retriever=MagicMock(),
        )
        chunk = _make_chunk(chunk_id=0, text="unique to bm25")
        chunk["lexical_score"] = 5.0

        fused = hybrid._fuse([], [chunk])

        assert len(fused) == 1
        assert fused[0]["lexical_score"] == 5.0
        assert "semantic_score" not in fused[0]


# ---------------------------------------------------------------------------
# 4. SemanticReranker — rerank_score attached
# ---------------------------------------------------------------------------

class TestSemanticRerankerScorePropagation:
    def test_rerank_score_attached(self):
        reranker = SemanticReranker()
        candidates = [
            _make_chunk(text="machine learning basics"),
            _make_chunk(text="deep learning neural networks"),
            _make_chunk(text="cooking recipes for beginners"),
        ]
        results = reranker.rerank("machine learning", candidates, k=3)

        assert len(results) == 3
        for chunk in results:
            assert "rerank_score" in chunk
            assert isinstance(chunk["rerank_score"], float)
            assert chunk["rerank_score"] >= 0.0

    def test_rerank_scores_ranked_best_first(self):
        reranker = SemanticReranker()
        candidates = [
            _make_chunk(chunk_id=0, text="unrelated topic about cooking"),
            _make_chunk(chunk_id=1, text="machine learning algorithms and models"),
            _make_chunk(chunk_id=2, text="the weather is nice today"),
        ]
        results = reranker.rerank("machine learning", candidates, k=3)

        scores = [c["rerank_score"] for c in results]
        assert scores == sorted(scores, reverse=True)

    def test_original_fields_preserved_after_rerank(self):
        reranker = SemanticReranker()
        candidates = [
            _make_chunk(filename="thesis.pdf", chunk_id=12, text="research findings"),
        ]
        results = reranker.rerank("research", candidates, k=1)

        assert len(results) == 1
        assert results[0]["filename"] == "thesis.pdf"
        assert results[0]["chunk_id"] == 12
        assert results[0]["text"] == "research findings"

    def test_rerank_with_empty_candidates(self):
        reranker = SemanticReranker()
        results = reranker.rerank("query", [], k=5)
        assert results == []

    def test_rerank_respects_k_limit(self):
        reranker = SemanticReranker()
        candidates = [
            _make_chunk(chunk_id=i, text=f"chunk {i} about machine learning")
            for i in range(10)
        ]
        results = reranker.rerank("machine learning", candidates, k=3)
        assert len(results) == 3


# ---------------------------------------------------------------------------
# 5. Full pipeline integration — scores flow end-to-end
# ---------------------------------------------------------------------------

class TestFullPipelineScoreFlow:
    def test_all_four_scores_present_after_hybrid_rerank(self):
        mock_semantic = MagicMock()
        mock_bm25 = MagicMock()

        chunk_s1 = _make_chunk(chunk_id=0, text="machine learning basics")
        chunk_s1["semantic_score"] = 0.80
        chunk_s2 = _make_chunk(chunk_id=1, text="deep learning networks")
        chunk_s2["semantic_score"] = 0.65

        chunk_k1 = _make_chunk(chunk_id=0, text="machine learning basics")
        chunk_k1["lexical_score"] = 4.5
        chunk_k2 = _make_chunk(chunk_id=2, text="cooking recipes")
        chunk_k2["lexical_score"] = 1.2

        mock_semantic.retrieve.return_value = [chunk_s1, chunk_s2]
        mock_bm25.retrieve.return_value = [chunk_k1, chunk_k2]

        hybrid = HybridRetriever(
            semantic_retriever=mock_semantic,
            bm25_retriever=mock_bm25,
        )
        results = hybrid.retrieve("machine learning", k=5, workspace_id="default", owner_id="u1")

        assert len(results) == 3
        for chunk in results:
            assert "rrf_score" in chunk
            assert "rerank_score" in chunk
            assert isinstance(chunk["rrf_score"], float)
            assert isinstance(chunk["rerank_score"], float)

        chunk_ids = [c["chunk_id"] for c in results]
        assert 0 in chunk_ids
        assert 1 in chunk_ids
        assert 2 in chunk_ids

    def test_scores_dont_break_prompt_builder(self):
        from app.services.llm.prompt_builder import PromptBuilder

        mock_semantic = MagicMock()
        mock_bm25 = MagicMock()

        chunk = _make_chunk(chunk_id=0, text="relevant context about AI")
        chunk["semantic_score"] = 0.85
        chunk["lexical_score"] = 3.2
        chunk["rrf_score"] = 0.033
        chunk["rerank_score"] = 0.75

        mock_semantic.retrieve.return_value = [chunk]
        mock_bm25.retrieve.return_value = []

        hybrid = HybridRetriever(semantic_retriever=mock_semantic, bm25_retriever=mock_bm25)
        results = hybrid.retrieve("AI", k=5, workspace_id="default", owner_id="u1")

        builder = PromptBuilder()
        prompt = builder.build_prompt("What is AI?", results)

        assert "relevant context about AI" in prompt.text
        assert len(prompt.sources) == 1
        assert prompt.sources[0]["filename"] == "doc.txt"
        assert prompt.sources[0]["chunk_id"] == 0


# ---------------------------------------------------------------------------
# 6. Ownership filtering unaffected
# ---------------------------------------------------------------------------

class TestOwnershipFilteringUnaffected:
    def test_semantic_retriever_respects_owner(self):
        mock_embedding_service = MagicMock()
        mock_vector_store = MagicMock()
        mock_metadata_store = MagicMock()
        mock_document_registry = _make_mock_registry()

        embedding = [0.1] * 384
        mock_embedding_service.generate_embeddings.return_value = [embedding]
        mock_vector_store.search.return_value = (np.array([[0.1, 0.2]]), np.array([[0, 1]]))
        mock_vector_store.ntotal = 2
        mock_vector_store.get_embedding.return_value = [0.1] * 384

        chunk_owner = _make_chunk(owner_id="alice", text="alice doc")
        chunk_other = _make_chunk(owner_id="bob", text="bob doc")
        mock_metadata_store.get_document.side_effect = [chunk_owner, chunk_other]

        retriever = SemanticRetriever(
            mock_embedding_service, mock_vector_store, mock_metadata_store, mock_document_registry
        )
        results = retriever.retrieve("test", k=5, workspace_id="default", owner_id="alice")

        assert len(results) == 1
        assert results[0]["owner_id"] == "alice"
        assert "semantic_score" in results[0]

    def test_bm25_retriever_respects_owner(self):
        mock_metadata_store = MagicMock()
        mock_document_registry = _make_mock_registry()

        chunks = [
            _make_chunk(owner_id="alice", text="machine learning"),
            _make_chunk(owner_id="bob", text="machine learning"),
        ]
        mock_metadata_store.get_all_documents.return_value = chunks
        mock_metadata_store.get_document.side_effect = lambda i: chunks[i]

        retriever = BM25Retriever(mock_metadata_store, mock_document_registry)
        results = retriever.retrieve("machine learning", k=5, workspace_id="default", owner_id="alice")

        for doc in results:
            assert doc["owner_id"] == "alice"
            assert "lexical_score" in doc

    def test_hybrid_retriever_respects_owner(self):
        mock_semantic = MagicMock()
        mock_bm25 = MagicMock()

        chunk_alice = _make_chunk(owner_id="alice", text="relevant")
        chunk_alice["semantic_score"] = 0.9
        chunk_alice["lexical_score"] = 5.0

        mock_semantic.retrieve.return_value = [chunk_alice]
        mock_bm25.retrieve.return_value = []

        hybrid = HybridRetriever(semantic_retriever=mock_semantic, bm25_retriever=mock_bm25)
        results = hybrid.retrieve("test", k=5, workspace_id="default", owner_id="alice")

        assert len(results) == 1
        assert results[0]["owner_id"] == "alice"
        mock_semantic.retrieve.assert_called_once_with(
            "test", k=5, workspace_id="default", owner_id="alice", query_embedding=None
        )


# ---------------------------------------------------------------------------
# 7. Backward compatibility — existing prompt builder tests pattern
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_chunk_with_scores_works_with_prompt_builder(self):
        from app.services.llm.prompt_builder import PromptBuilder

        contexts = [
            {
                "id": 1,
                "workspace_id": "default",
                "filename": "resume.pdf",
                "chunk_id": 0,
                "document_id": "d1",
                "owner_id": "u1",
                "text": "John Doe, Software Engineer",
                "semantic_score": 0.82,
                "lexical_score": 3.5,
                "rrf_score": 0.032,
                "rerank_score": 0.71,
            },
        ]

        builder = PromptBuilder()
        prompt = builder.build_prompt("What is the candidate's name?", contexts)

        assert "John Doe" in prompt.text
        assert len(prompt.sources) == 1
        assert prompt.sources[0]["filename"] == "resume.pdf"
        assert prompt.sources[0]["chunk_id"] == 0

    def test_chunk_without_scores_still_works(self):
        from app.services.llm.prompt_builder import PromptBuilder

        contexts = [
            {"text": "legacy content", "filename": "old.txt", "chunk_id": 0},
        ]

        builder = PromptBuilder()
        prompt = builder.build_prompt("What is this?", contexts)

        assert "legacy content" in prompt.text
        assert len(prompt.sources) == 1
