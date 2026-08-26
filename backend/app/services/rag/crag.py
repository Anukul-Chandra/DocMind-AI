"""Corrective retrieval orchestration for Adaptive CRAG (Part 3B).

This module connects the existing :class:`~app.services.rag.query_rewriter.QueryRewriter`
and :class:`~app.services.rag.retrieval_evaluator.RetrievalEvaluator` to the
existing :class:`~app.services.retrieval.base.Retriever` through a small
orchestration layer.

Flow (DOCUMENT queries only, enforced by the caller):

    1. Retrieve contexts for the original query.
    2. Evaluate retrieval quality.
    3. If GOOD: keep the original contexts, no rewrite.
    4. Else: rewrite the query ONCE and retrieve again.
    5. If the corrective retrieval is empty or raises, fall back to the
       original contexts.

Hard limits (never exceeded in a single call):

    - at most 1 rewrite
    - at most 2 retrieval passes
    - at most 2 evaluations
    - no recursive CRAG calls

The orchestrator is provider-agnostic: it only depends on the retriever,
evaluator, and rewriter abstractions passed to it.  It never touches the
final answer prompt — the caller remains responsible for building the prompt
from the original question and the returned (possibly corrected) contexts.
"""

from __future__ import annotations

import logging

from app.services.rag.query_rewriter import QueryRewriter
from app.services.rag.retrieval_evaluator import (
    RetrievalEvaluation,
    RetrievalEvaluator,
    RetrievalQuality,
)
from app.services.retrieval.base import Retriever
from app.services.vectorstore.workspace import DEFAULT_WORKSPACE

logger = logging.getLogger(__name__)


class CragOrchestrator:
    """Orchestrate a single corrective-retrieval pass for DOCUMENT queries.

    Args:
        retriever: The shared retriever used for both passes.
        evaluator: Scores retrieval quality.  If None the orchestrator
            degenerates to a single plain retrieval (no correction).
        rewriter: Rewrites a weak query into a better retrieval query.  If
            None the orchestrator degenerates to a single plain retrieval.
    """

    def __init__(
        self,
        retriever: Retriever,
        evaluator: RetrievalEvaluator | None = None,
        rewriter: QueryRewriter | None = None,
    ) -> None:
        self._retriever = retriever
        self._evaluator = evaluator
        self._rewriter = rewriter

    async def retrieve(
        self,
        query: str,
        *,
        owner_id: str = "",
        workspace_id: str = DEFAULT_WORKSPACE,
        k: int = 5,
        query_embedding: list[float] | None = None,
    ) -> list[dict]:
        """Retrieve contexts, applying at most one corrective rewrite.

        Args:
            query: The original user question (used verbatim for the first
                retrieval and for the evaluation calls).
            owner_id: Ownership scope for retrieval (never crossed).
            workspace_id: Workspace scope for retrieval.
            k: Number of chunks to return per pass.
            query_embedding: Precomputed embedding for the original query,
                forwarded to the first retrieval.  The corrective retrieval
                passes ``None`` so the retriever embeds the rewritten query
                freshly.

        Returns:
            The final selected contexts: the original retrieval on GOOD
            quality, or the corrective retrieval when it succeeds and is
            non-empty.  Falls back to the original contexts in every failure
            mode so the chat request is never broken by CRAG.
        """
        contexts = self._retriever.retrieve(
            query,
            k=k,
            workspace_id=workspace_id,
            owner_id=owner_id,
            query_embedding=query_embedding,
        )

        # Without an evaluator or rewriter we cannot make a corrective
        # decision — behave exactly like plain retrieval.
        if self._evaluator is None or self._rewriter is None:
            return contexts

        # First evaluation (count: 1).
        evaluation: RetrievalEvaluation = self._evaluator.evaluate(query, contexts)
        if evaluation.quality is RetrievalQuality.GOOD:
            return contexts

        # One rewrite, maximum.  The rewriter is itself safe: it returns the
        # original query on any failure, which we detect to skip correction.
        try:
            rewritten = await self._rewriter.rewrite(query)
        except Exception as exc:  # defensive: never break the chat request
            logger.warning("CRAG rewrite failed; using original contexts: %s", exc)
            return contexts

        if not rewritten or rewritten == query:
            # Rewrite produced nothing usable (failure/empty/overlong).
            return contexts

        # Second retrieval pass (count: 2).  Fresh embedding for the rewrite.
        try:
            corrected = self._retriever.retrieve(
                rewritten,
                k=k,
                workspace_id=workspace_id,
                owner_id=owner_id,
                query_embedding=None,
            )
        except Exception as exc:  # corrective retrieval failure → fall back
            logger.warning(
                "CRAG corrective retrieval failed; using original contexts: %s",
                exc,
            )
            return contexts

        # Empty corrective retrieval is "nothing useful" → fall back.
        if not corrected:
            logger.info("CRAG corrective retrieval empty; using original contexts.")
            return contexts

        # Second evaluation (count: 2).  Computed for observability/consistency
        # with the CRAG design; the corrected contexts are used as final unless
        # empty/failed (handled above).
        self._evaluator.evaluate(rewritten, corrected)

        return corrected
