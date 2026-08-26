"""Deterministic retrieval quality evaluation for Adaptive CRAG.

Evaluates the quality of retrieved chunks using only the score metadata
propagated by the retrieval pipeline (semantic_score, lexical_score,
rrf_score, rerank_score).  Makes **zero** LLM or provider calls — every
decision is computed from existing numeric signals.

Score scales (from the retrieval pipeline):

    semantic_score  – cosine similarity via MiniLM embeddings, [0, 1].
    lexical_score   – Okapi BM25 score, [0, +∞).  0.0 = no keyword match.
    rrf_score       – reciprocal rank fusion (K=60), (0, ~0.0167].
    rerank_score    – token-level cosine similarity, [0, 1].

Thresholds are configurable and documented.  Missing score fields are
treated as 0.0 so the evaluator never crashes on incomplete data.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RetrievalQuality(Enum):
    """Routing decision produced by the evaluator."""

    GOOD = "good"
    UNCERTAIN = "uncertain"
    BAD = "bad"


@dataclass(frozen=True)
class RetrievalEvaluation:
    """Structured result of retrieval quality evaluation.

    Attributes:
        quality: The routing decision (GOOD / UNCERTAIN / BAD).
        confidence: A [0, 1] score reflecting how many independent signals
            agree on the decision.  0.0 = no confidence, 1.0 = maximum.
        reason: A short human-readable explanation of the decision.
        best_semantic: The highest ``semantic_score`` across all chunks.
        best_rerank: The highest ``rerank_score`` across all chunks.
        best_lexical: The highest ``lexical_score`` across all chunks.
        best_rrf: The highest ``rrf_score`` across all chunks.
        context_count: The number of retrieved chunks evaluated.
    """

    quality: RetrievalQuality
    confidence: float
    reason: str
    best_semantic: float
    best_rerank: float
    best_lexical: float
    best_rrf: float
    context_count: int


class RetrievalEvaluator:
    """Evaluate retrieval quality from chunk score metadata.

    The evaluator is a pure, provider-agnostic service.  It receives the
    chunks returned by the retrieval pipeline and produces a structured
    :class:`RetrievalEvaluation` without any external calls.

    Thresholds:

        good_semantic_floor (default 0.35):
            Minimum ``semantic_score`` (cosine similarity) for a chunk to be
            considered semantically strong.  Below this, the chunk's embedding
            has only marginal overlap with the query.

        uncertain_semantic_floor (default 0.15):
            Minimum ``semantic_score`` for the retrieval to avoid being
            classified as BAD.  Anything above this indicates *some* signal,
            even if weak.

        good_rerank_floor (default 0.5):
            Minimum ``rerank_score`` (token cosine) for a chunk to count as
            strong lexical evidence.  A score of 0.5 means roughly half the
            query tokens appear in the chunk.

        min_strong_chunks (default 2):
            Minimum number of chunks at or above ``good_semantic_floor``
            required for a GOOD decision.  A single strong chunk may be a
            false positive; two or more provide corroborating evidence.
    """

    def __init__(
        self,
        good_semantic_floor: float = 0.35,
        uncertain_semantic_floor: float = 0.15,
        good_rerank_floor: float = 0.5,
        min_strong_chunks: int = 2,
    ) -> None:
        self._good_semantic_floor = good_semantic_floor
        self._uncertain_semantic_floor = uncertain_semantic_floor
        self._good_rerank_floor = good_rerank_floor
        self._min_strong_chunks = min_strong_chunks

    def evaluate(
        self,
        query: str,
        chunks: list[dict],
    ) -> RetrievalEvaluation:
        """Evaluate retrieval quality for the given chunks.

        Args:
            query: The original user query (used for context in the reason
                string; not used for scoring).
            chunks: The retrieved chunk metadata dicts, each optionally
                containing ``semantic_score``, ``lexical_score``,
                ``rrf_score``, and ``rerank_score``.

        Returns:
            A :class:`RetrievalEvaluation` with the quality decision,
            confidence, reason, and extracted best scores.
        """
        if not chunks:
            return RetrievalEvaluation(
                quality=RetrievalQuality.BAD,
                confidence=1.0,
                reason="No chunks retrieved.",
                best_semantic=0.0,
                best_rerank=0.0,
                best_lexical=0.0,
                best_rrf=0.0,
                context_count=0,
            )

        best_semantic = max(c.get("semantic_score", 0.0) for c in chunks)
        best_rerank = max(c.get("rerank_score", 0.0) for c in chunks)
        best_lexical = max(c.get("lexical_score", 0.0) for c in chunks)
        best_rrf = max(c.get("rrf_score", 0.0) for c in chunks)
        context_count = len(chunks)

        n_strong = sum(
            1 for c in chunks
            if c.get("semantic_score", 0.0) >= self._good_semantic_floor
        )

        quality, reason = self._classify(
            best_semantic=best_semantic,
            best_rerank=best_rerank,
            best_lexical=best_lexical,
            n_strong=n_strong,
            context_count=context_count,
        )

        confidence = self._compute_confidence(
            best_semantic=best_semantic,
            best_rerank=best_rerank,
            best_lexical=best_lexical,
            n_strong=n_strong,
            context_count=context_count,
        )

        return RetrievalEvaluation(
            quality=quality,
            confidence=confidence,
            reason=reason,
            best_semantic=best_semantic,
            best_rerank=best_rerank,
            best_lexical=best_lexical,
            best_rrf=best_rrf,
            context_count=context_count,
        )

    def _classify(
        self,
        best_semantic: float,
        best_rerank: float,
        best_lexical: float,
        n_strong: int,
        context_count: int,
    ) -> tuple[RetrievalQuality, str]:
        """Apply the decision matrix to the collected signals.

        Priority order:
            1. GOOD — multiple chunks with strong semantic evidence.
            2. UNCERTAIN — some evidence from any signal (semantic, rerank,
               or lexical) but not enough for GOOD.
            3. BAD — no meaningful evidence in any signal.
        """
        # --- GOOD ---
        if (
            best_semantic >= self._good_semantic_floor
            and n_strong >= self._min_strong_chunks
        ):
            return (
                RetrievalQuality.GOOD,
                (
                    f"{n_strong} chunks with semantic_score >= "
                    f"{self._good_semantic_floor:.2f} (best {best_semantic:.3f})"
                ),
            )

        # --- UNCERTAIN ---
        if best_semantic >= self._uncertain_semantic_floor:
            return (
                RetrievalQuality.UNCERTAIN,
                (
                    f"Weak semantic evidence (best {best_semantic:.3f}, "
                    f"floor {self._uncertain_semantic_floor:.2f})"
                ),
            )
        if best_rerank >= self._good_rerank_floor:
            return (
                RetrievalQuality.UNCERTAIN,
                f"Strong rerank score ({best_rerank:.3f}) but weak semantic ({best_semantic:.3f})",
            )
        if best_lexical > 0.0:
            return (
                RetrievalQuality.UNCERTAIN,
                f"Keyword match (lexical {best_lexical:.3f}) but weak semantic ({best_semantic:.3f})",
            )

        # --- BAD ---
        return (
            RetrievalQuality.BAD,
            f"No meaningful evidence (semantic {best_semantic:.3f}, rerank {best_rerank:.3f}, lexical {best_lexical:.3f})",
        )

    @staticmethod
    def _compute_confidence(
        best_semantic: float,
        best_rerank: float,
        best_lexical: float,
        n_strong: int,
        context_count: int,
    ) -> float:
        """Compute a [0, 1] confidence score from independent signals.

        Each signal contributes a fixed weight when present.  The total is
        clamped to [0, 1].  This is a heuristic — not a probability.
        """
        confidence = 0.0

        # Semantic strength (0.30)
        if best_semantic >= 0.35:
            confidence += 0.30
        elif best_semantic >= 0.15:
            confidence += 0.15

        # Corroboration (0.20)
        if n_strong >= 2:
            confidence += 0.20

        # Rerank evidence (0.20)
        if best_rerank >= 0.5:
            confidence += 0.20
        elif best_rerank >= 0.2:
            confidence += 0.10

        # Lexical evidence (0.15)
        if best_lexical > 0.0:
            confidence += 0.15

        # Context volume (0.15)
        if context_count >= 3:
            confidence += 0.15
        elif context_count >= 1:
            confidence += 0.05

        return min(confidence, 1.0)
