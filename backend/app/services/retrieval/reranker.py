"""Reranking layer for the retrieval pipeline."""

import math
import re
from abc import ABC, abstractmethod
from collections import Counter
from typing import Protocol

TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


class Reranker(Protocol):
    """Interface for reranking retrieved document chunks.

    Implementations replace the default reranker without changing
    ``ChatService`` or ``HybridRetriever``. Providers such as Cohere, Jina AI,
    BGE, VoyageAI, and NVIDIA NIM can supply their own implementation of this
    protocol in the future.
    """

    def rerank(
        self,
        query: str,
        candidates: list[dict],
        k: int = 5,
    ) -> list[dict]:
        """Rerank a list of candidate chunks for relevance to a query.

        Args:
            query: The search query text.
            candidates: The candidate chunks to rerank, each a dict with text.
            k: The number of best chunks to return.

        Returns:
            The best ``k`` candidates ordered by relevance (best first).
        """


class DefaultReranker(ABC):
    """Base class shared by the lightweight default reranker.

    Declared so future provider-based rerankers can extend a common shape if
    desired, while staying optional. The ``rerank`` method is provided via the
    abstract method below for the built-in, dependency-free implementation.
    """

    @abstractmethod
    def rerank(
        self,
        query: str,
        candidates: list[dict],
        k: int = 5,
    ) -> list[dict]:
        """Rerank candidate chunks via lightweight semantic similarity.

        Args:
            query: The search query text.
            candidates: The candidate chunks to rerank.
            k: The number of best chunks to return.

        Returns:
            The best ``k`` chunks ordered by descending score.
        """

    @staticmethod
    def _score(query_tokens: Counter[str], text: str) -> float:
        """Compute a lightweight semantic similarity score.

        Uses the cosine similarity of term-frequency vectors (query vs. chunk)
        with added weight for shared terms. Purely dependency-free.

        Args:
            query_tokens: The query's term-frequency vector.
            text: The candidate chunk text.

        Returns:
            A similarity score in ``[0, 1]``.
        """
        text_tokens = Counter(TOKEN_PATTERN.findall(text.lower()))
        if not query_tokens or not text_tokens:
            return 0.0

        shared = query_tokens & text_tokens
        if not shared:
            return 0.0

        dot = sum(query_tokens[term] * text_tokens[term] for term in shared)
        norm_query = math.sqrt(sum(v * v for v in query_tokens.values()))
        norm_text = math.sqrt(sum(v * v for v in text_tokens.values()))
        if not norm_query or not norm_text:
            return 0.0
        return dot / (norm_query * norm_text)


class SemanticReranker(DefaultReranker):
    """Default dependency-free reranker built on token-level similarity.

    Scores each candidate chunk by how similar its tokens are to the query
    tokens, sorts by descending score, and returns the top ``k`` chunks. No
    external libraries are required.
    """

    def rerank(
        self,
        query: str,
        candidates: list[dict],
        k: int = 5,
    ) -> list[dict]:
        """Rerank candidate chunks by lightweight semantic similarity.

        Args:
            query: The search query text.
            candidates: The candidate chunks to rerank.
            k: The number of best chunks to return.

        Returns:
            The best ``k`` chunks ordered by descending similarity score.
        """
        query_tokens = Counter(TOKEN_PATTERN.findall(query.lower()))
        scored = [
            (self._score(query_tokens, candidate.get("text", "")), candidate, i)
            for i, candidate in enumerate(candidates)
        ]
        scored.sort(key=lambda pair: (-pair[0], pair[2]))
        result: list[dict] = []
        for rerank_score, candidate, _ in scored[:k]:
            candidate["rerank_score"] = rerank_score
            result.append(candidate)
        return result