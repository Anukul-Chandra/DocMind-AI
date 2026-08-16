"""Hybrid retrieval combining BM25 keyword search and FAISS semantic search."""

from collections import defaultdict

from app.services.retrieval.base import Retriever
from app.services.retrieval.reranker import Reranker, SemanticReranker
from app.services.vectorstore.workspace import DEFAULT_WORKSPACE


class HybridRetriever(Retriever):
    """Retrieve chunks by merging BM25 and semantic (FAISS) search results.

    Workflow per query:
        1. Run BM25 keyword search.
        2. Run FAISS semantic search.
        3. Merge both result lists.
        4. Remove duplicate chunks (a single chunk may appear in both lists).
        5. Rank combined results by reciprocal rank fusion (RRF).
        6. Rerank the fused results with an injected reranker.
        7. Return the top-k chunks.
    """

    RRF_K = 60.0

    def __init__(
        self,
        semantic_retriever: Retriever,
        bm25_retriever: Retriever,
        reranker: Reranker | None = None,
    ) -> None:
        """Initialize the hybrid retriever with its sub-retrievers.

        The reranker defaults to the dependency-free ``SemanticReranker``; pass
        a different ``Reranker`` implementation (e.g. a Cohere or BGE-powered
        one) to swap it without changing callers.

        Args:
            semantic_retriever: The FAISS-backed semantic retriever.
            bm25_retriever: The keyword-backed BM25 retriever.
            reranker: The reranker used to reorder fused results.
        """
        self._semantic = semantic_retriever
        self._bm25 = bm25_retriever
        self._reranker = reranker or SemanticReranker()

    def retrieve(
        self,
        query: str,
        k: int = 5,
        workspace_id: str = DEFAULT_WORKSPACE,
        owner_id: str = "",
        query_embedding: list[float] | None = None,
    ) -> list[dict]:
        """Retrieve and rerank the top-k chunks combining BM25 and FAISS.

        Args:
            query: The search query text.
            k: The number of chunks to return.
            workspace_id: Only chunks belonging to this workspace are returned.
            owner_id: Only chunks owned by this user are returned. Empty for
                legacy chunks indexed before ownership was tracked.
            query_embedding: A precomputed query embedding forwarded to the
                semantic sub-retriever to avoid a duplicate embedding.

        Returns:
            The top-k merged, deduplicated, reranked chunks (best first),
            constrained to the workspace and owner.
        """
        semantic_results = self._semantic.retrieve(
            query,
            k=k,
            workspace_id=workspace_id,
            owner_id=owner_id,
            query_embedding=query_embedding,
        )
        keyword_results = self._bm25.retrieve(
            query, k=k, workspace_id=workspace_id, owner_id=owner_id
        )

        fused = self._fuse(semantic_results, keyword_results)
        return self._reranker.rerank(query, fused, k=k)

    def _fuse(
        self,
        semantic_results: list[dict],
        keyword_results: list[dict],
    ) -> list[dict]:
        """Merge and rank two ranked result lists using reciprocal rank.

        Args:
            semantic_results: Chunks ranked by FAISS (best first).
            keyword_results: Chunks ranked by BM25 (best first).

        Returns:
            A deduplicated list of chunks ranked by fusion score (best first).
        """
        scores: dict[tuple, float] = defaultdict(float)
        lookup: dict[tuple, dict] = {}

        for rank, candidate in enumerate(semantic_results):
            key = self._key(candidate)
            scores[key] += 1.0 / (self.RRF_K + rank)
            lookup.setdefault(key, candidate)

        for rank, candidate in enumerate(keyword_results):
            key = self._key(candidate)
            scores[key] += 1.0 / (self.RRF_K + rank)
            lookup.setdefault(key, candidate)

        ranked = sorted(
            scores.items(),
            key=lambda item: item[1],
            reverse=True,
        )
        return [lookup[key] for key, _ in ranked]

    @staticmethod
    def _key(candidate: dict) -> tuple:
        """Return a stable identity key for a chunk.

        Args:
            candidate: The chunk metadata.

        Returns:
            A tuple identifying the chunk across retrieval methods.
        """
        return (
            candidate["workspace_id"],
            candidate["filename"],
            candidate["chunk_id"],
        )

    def is_eligible(
        self,
        document: dict,
        workspace_id: str,
        owner_id: str = "",
    ) -> bool:
        """Delegate eligibility to the semantic sub-retriever.

        Args:
            document: The chunk metadata to check.
            workspace_id: The requested workspace.
            owner_id: The requested owner.

        Returns:
            Whether the chunk is eligible for the workspace and owner.
        """
        return self._semantic.is_eligible(document, workspace_id, owner_id)