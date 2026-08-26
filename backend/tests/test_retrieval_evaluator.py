"""Deterministic tests for RetrievalEvaluator.

Covers:
1. Strong retrieval → GOOD
2. Weak retrieval → UNCERTAIN
3. Empty retrieval → BAD
4. Missing score → safe handling
5. Multiple chunks → deterministic result
6. Score ordering → deterministic result
7. No provider calls
8. Custom thresholds
9. Confidence scoring
"""

from unittest.mock import MagicMock

import pytest

from app.services.rag.retrieval_evaluator import (
    RetrievalEvaluator,
    RetrievalEvaluation,
    RetrievalQuality,
)


def _chunk(
    semantic: float = 0.0,
    lexical: float = 0.0,
    rrf: float = 0.0,
    rerank: float = 0.0,
    **extra,
) -> dict:
    """Build a chunk dict with optional score fields."""
    d: dict = {"text": "x", "filename": "f.txt", "chunk_id": 0, **extra}
    if semantic:
        d["semantic_score"] = semantic
    if lexical:
        d["lexical_score"] = lexical
    if rrf:
        d["rrf_score"] = rrf
    if rerank:
        d["rerank_score"] = rerank
    return d


# ---------------------------------------------------------------------------
# 1. Strong retrieval → GOOD
# ---------------------------------------------------------------------------

class TestGoodQuality:
    def test_two_strong_chunks_is_good(self):
        ev = RetrievalEvaluator()
        chunks = [
            _chunk(semantic=0.45, rerank=0.6, lexical=3.0, rrf=0.016),
            _chunk(semantic=0.40, rerank=0.55, lexical=2.5, rrf=0.015),
        ]
        result = ev.evaluate("What is in my CV?", chunks)
        assert result.quality == RetrievalQuality.GOOD
        assert result.context_count == 2

    def test_three_strong_chunks_is_good(self):
        ev = RetrievalEvaluator()
        chunks = [
            _chunk(semantic=0.50, rerank=0.7, lexical=4.0, rrf=0.016),
            _chunk(semantic=0.42, rerank=0.6, lexical=3.5, rrf=0.015),
            _chunk(semantic=0.38, rerank=0.55, lexical=2.0, rrf=0.014),
        ]
        result = ev.evaluate("Summarize my resume", chunks)
        assert result.quality == RetrievalQuality.GOOD
        assert result.context_count == 3

    def test_high_scores_reflect_in_best_fields(self):
        ev = RetrievalEvaluator()
        chunks = [
            _chunk(semantic=0.60, rerank=0.80, lexical=5.0, rrf=0.016),
            _chunk(semantic=0.45, rerank=0.50, lexical=2.0, rrf=0.010),
        ]
        result = ev.evaluate("q", chunks)
        assert result.best_semantic == 0.60
        assert result.best_rerank == 0.80
        assert result.best_lexical == 5.0
        assert result.best_rrf == 0.016


# ---------------------------------------------------------------------------
# 2. Weak retrieval → UNCERTAIN
# ---------------------------------------------------------------------------

class TestUncertainQuality:
    def test_single_strong_chunk_is_uncertain(self):
        ev = RetrievalEvaluator()
        chunks = [
            _chunk(semantic=0.40, rerank=0.5, lexical=2.0, rrf=0.016),
        ]
        result = ev.evaluate("What does my CV say?", chunks)
        assert result.quality == RetrievalQuality.UNCERTAIN

    def test_weak_semantic_is_uncertain(self):
        ev = RetrievalEvaluator()
        chunks = [
            _chunk(semantic=0.20, rerank=0.3, lexical=1.0, rrf=0.010),
            _chunk(semantic=0.18, rerank=0.2, lexical=0.5, rrf=0.009),
        ]
        result = ev.evaluate("Explain my resume", chunks)
        assert result.quality == RetrievalQuality.UNCERTAIN

    def test_strong_rerank_weak_semantic_is_uncertain(self):
        ev = RetrievalEvaluator()
        chunks = [
            _chunk(semantic=0.10, rerank=0.60, lexical=0.0, rrf=0.010),
        ]
        result = ev.evaluate("q", chunks)
        assert result.quality == RetrievalQuality.UNCERTAIN

    def test_lexical_only_is_uncertain(self):
        ev = RetrievalEvaluator()
        chunks = [
            _chunk(semantic=0.05, rerank=0.1, lexical=2.5, rrf=0.008),
            _chunk(semantic=0.08, rerank=0.05, lexical=1.8, rrf=0.007),
        ]
        result = ev.evaluate("skills experience", chunks)
        assert result.quality == RetrievalQuality.UNCERTAIN


# ---------------------------------------------------------------------------
# 3. Empty retrieval → BAD
# ---------------------------------------------------------------------------

class TestBadQuality:
    def test_empty_chunks_is_bad(self):
        ev = RetrievalEvaluator()
        result = ev.evaluate("What is in my CV?", [])
        assert result.quality == RetrievalQuality.BAD
        assert result.confidence == 1.0
        assert result.context_count == 0
        assert result.best_semantic == 0.0
        assert result.best_rerank == 0.0
        assert result.best_lexical == 0.0
        assert result.best_rrf == 0.0

    def test_all_zero_scores_is_bad(self):
        ev = RetrievalEvaluator()
        chunks = [
            _chunk(semantic=0.0, rerank=0.0, lexical=0.0, rrf=0.0),
            _chunk(semantic=0.0, rerank=0.0, lexical=0.0, rrf=0.0),
        ]
        result = ev.evaluate("quantum computing", chunks)
        assert result.quality == RetrievalQuality.BAD

    def test_very_low_scores_is_bad(self):
        ev = RetrievalEvaluator()
        chunks = [
            _chunk(semantic=0.05, rerank=0.05, lexical=0.0, rrf=0.001),
        ]
        result = ev.evaluate("random unrelated query", chunks)
        assert result.quality == RetrievalQuality.BAD


# ---------------------------------------------------------------------------
# 4. Missing score → safe handling
# ---------------------------------------------------------------------------

class TestMissingScores:
    def test_no_semantic_score(self):
        ev = RetrievalEvaluator()
        chunks = [{"text": "x", "filename": "f.txt", "chunk_id": 0}]
        result = ev.evaluate("q", chunks)
        assert result.quality == RetrievalQuality.BAD
        assert result.best_semantic == 0.0

    def test_partial_scores(self):
        ev = RetrievalEvaluator()
        chunks = [
            _chunk(semantic=0.40, lexical=2.0),
        ]
        result = ev.evaluate("q", chunks)
        assert result.quality == RetrievalQuality.UNCERTAIN
        assert result.best_rerank == 0.0
        assert result.best_rrf == 0.0

    def test_only_rrf_present(self):
        ev = RetrievalEvaluator()
        chunks = [
            _chunk(rrf=0.016),
        ]
        result = ev.evaluate("q", chunks)
        assert result.quality == RetrievalQuality.BAD
        assert result.best_rrf == 0.016

    def test_mixed_missing_and_present(self):
        ev = RetrievalEvaluator()
        chunks = [
            {"text": "a", "filename": "f.txt", "chunk_id": 0, "semantic_score": 0.50},
            {"text": "b", "filename": "g.txt", "chunk_id": 1, "rerank_score": 0.70},
            {"text": "c", "filename": "h.txt", "chunk_id": 2},
        ]
        result = ev.evaluate("q", chunks)
        assert result.best_semantic == 0.50
        assert result.best_rerank == 0.70
        assert result.best_lexical == 0.0
        assert result.context_count == 3


# ---------------------------------------------------------------------------
# 5. Multiple chunks → deterministic result
# ---------------------------------------------------------------------------

class TestDeterministicResults:
    def test_same_input_same_output(self):
        ev = RetrievalEvaluator()
        chunks = [
            _chunk(semantic=0.45, rerank=0.6, lexical=3.0, rrf=0.016),
            _chunk(semantic=0.40, rerank=0.55, lexical=2.5, rrf=0.015),
        ]
        r1 = ev.evaluate("q", chunks)
        r2 = ev.evaluate("q", chunks)
        assert r1.quality == r2.quality
        assert r1.confidence == r2.confidence
        assert r1.reason == r2.reason
        assert r1.best_semantic == r2.best_semantic
        assert r1.best_rerank == r2.best_rerank
        assert r1.best_lexical == r2.best_lexical
        assert r1.best_rrf == r2.best_rrf
        assert r1.context_count == r2.context_count

    def test_deterministic_across_many_calls(self):
        ev = RetrievalEvaluator()
        chunks = [_chunk(semantic=0.20, rerank=0.15, lexical=1.0, rrf=0.008)]
        results = [ev.evaluate("q", chunks) for _ in range(50)]
        qualities = [r.quality for r in results]
        assert len(set(qualities)) == 1
        confidences = [r.confidence for r in results]
        assert len(set(confidences)) == 1


# ---------------------------------------------------------------------------
# 6. Score ordering → deterministic result
# ---------------------------------------------------------------------------

class TestScoreOrdering:
    def test_best_scores_are_max(self):
        ev = RetrievalEvaluator()
        chunks = [
            _chunk(semantic=0.30, rerank=0.40, lexical=1.0, rrf=0.010),
            _chunk(semantic=0.50, rerank=0.60, lexical=3.0, rrf=0.016),
            _chunk(semantic=0.20, rerank=0.30, lexical=0.5, rrf=0.008),
        ]
        result = ev.evaluate("q", chunks)
        assert result.best_semantic == 0.50
        assert result.best_rerank == 0.60
        assert result.best_lexical == 3.0
        assert result.best_rrf == 0.016

    def test_single_chunk_best_equals_only(self):
        ev = RetrievalEvaluator()
        chunks = [_chunk(semantic=0.25, rerank=0.35, lexical=1.5, rrf=0.012)]
        result = ev.evaluate("q", chunks)
        assert result.best_semantic == 0.25
        assert result.best_rerank == 0.35
        assert result.best_lexical == 1.5
        assert result.best_rrf == 0.012


# ---------------------------------------------------------------------------
# 7. No provider calls
# ---------------------------------------------------------------------------

class TestNoProviderCalls:
    def test_evaluator_makes_no_external_calls(self):
        ev = RetrievalEvaluator()
        chunks = [_chunk(semantic=0.50, rerank=0.6, lexical=3.0, rrf=0.016)]
        result = ev.evaluate("What is in my CV?", chunks)
        assert isinstance(result, RetrievalEvaluation)
        assert isinstance(result.quality, RetrievalQuality)

    def test_evaluator_is_stateless(self):
        ev1 = RetrievalEvaluator()
        ev2 = RetrievalEvaluator()
        chunks = [_chunk(semantic=0.40, rerank=0.5, lexical=2.0, rrf=0.014)]
        r1 = ev1.evaluate("q", chunks)
        r2 = ev2.evaluate("q", chunks)
        assert r1.quality == r2.quality
        assert r1.confidence == r2.confidence


# ---------------------------------------------------------------------------
# 8. Custom thresholds
# ---------------------------------------------------------------------------

class TestCustomThresholds:
    def test_higher_good_floor_requires_higher_scores(self):
        ev = RetrievalEvaluator(good_semantic_floor=0.60)
        chunks = [
            _chunk(semantic=0.50, rerank=0.6, lexical=3.0, rrf=0.016),
            _chunk(semantic=0.45, rerank=0.55, lexical=2.5, rrf=0.015),
        ]
        result = ev.evaluate("q", chunks)
        assert result.quality == RetrievalQuality.UNCERTAIN

    def test_lower_min_strong_chunks_allows_good_faster(self):
        ev = RetrievalEvaluator(min_strong_chunks=1)
        chunks = [
            _chunk(semantic=0.40, rerank=0.5, lexical=2.0, rrf=0.014),
        ]
        result = ev.evaluate("q", chunks)
        assert result.quality == RetrievalQuality.GOOD

    def test_custom_uncertain_floor(self):
        ev = RetrievalEvaluator(uncertain_semantic_floor=0.30)
        chunks = [_chunk(semantic=0.20, rerank=0.1, lexical=0.0, rrf=0.005)]
        result = ev.evaluate("q", chunks)
        assert result.quality == RetrievalQuality.BAD


# ---------------------------------------------------------------------------
# 9. Confidence scoring
# ---------------------------------------------------------------------------

class TestConfidence:
    def test_empty_confidence_is_one(self):
        ev = RetrievalEvaluator()
        result = ev.evaluate("q", [])
        assert result.confidence == 1.0

    def test_strong_signals_high_confidence(self):
        ev = RetrievalEvaluator()
        chunks = [
            _chunk(semantic=0.50, rerank=0.70, lexical=4.0, rrf=0.016),
            _chunk(semantic=0.45, rerank=0.60, lexical=3.0, rrf=0.015),
            _chunk(semantic=0.40, rerank=0.55, lexical=2.5, rrf=0.014),
        ]
        result = ev.evaluate("q", chunks)
        assert result.confidence >= 0.80

    def test_weak_signals_low_confidence(self):
        ev = RetrievalEvaluator()
        chunks = [
            _chunk(semantic=0.05, rerank=0.05, lexical=0.0, rrf=0.001),
        ]
        result = ev.evaluate("q", chunks)
        assert result.confidence <= 0.20

    def test_confidence_is_bounded(self):
        ev = RetrievalEvaluator()
        chunks = [
            _chunk(semantic=0.99, rerank=0.99, lexical=100.0, rrf=0.016),
            _chunk(semantic=0.98, rerank=0.98, lexical=99.0, rrf=0.016),
            _chunk(semantic=0.97, rerank=0.97, lexical=98.0, rrf=0.016),
        ]
        result = ev.evaluate("q", chunks)
        assert 0.0 <= result.confidence <= 1.0

    def test_confidence_increases_with_more_signals(self):
        ev = RetrievalEvaluator()
        # Only semantic
        r1 = ev.evaluate("q", [_chunk(semantic=0.50)])
        # Semantic + rerank
        r2 = ev.evaluate("q", [_chunk(semantic=0.50, rerank=0.60)])
        # Semantic + rerank + lexical
        r3 = ev.evaluate("q", [_chunk(semantic=0.50, rerank=0.60, lexical=3.0)])
        assert r1.confidence <= r2.confidence <= r3.confidence


# ---------------------------------------------------------------------------
# 10. Reason strings
# ---------------------------------------------------------------------------

class TestReasonStrings:
    def test_good_reason_mentions_chunk_count(self):
        ev = RetrievalEvaluator()
        chunks = [
            _chunk(semantic=0.45, rerank=0.6, lexical=3.0, rrf=0.016),
            _chunk(semantic=0.40, rerank=0.55, lexical=2.5, rrf=0.015),
        ]
        result = ev.evaluate("q", chunks)
        assert "2 chunks" in result.reason
        assert "semantic_score" in result.reason

    def test_bad_empty_reason(self):
        ev = RetrievalEvaluator()
        result = ev.evaluate("q", [])
        assert "No chunks" in result.reason

    def test_bad_no_evidence_reason(self):
        ev = RetrievalEvaluator()
        chunks = [_chunk(semantic=0.05, rerank=0.03, lexical=0.0, rrf=0.001)]
        result = ev.evaluate("q", chunks)
        assert "No meaningful evidence" in result.reason
