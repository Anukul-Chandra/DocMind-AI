"""Corrective retrieval orchestration for Adaptive CRAG (Parts 3B/3C).

This module connects the existing :class:`~app.services.rag.query_rewriter.QueryRewriter`
and :class:`~app.services.rag.retrieval_evaluator.RetrievalEvaluator` to the
existing :class:`~app.services.retrieval.base.Retriever` through a small
orchestration layer.

Flow (DOCUMENT queries only, enforced by the caller):

    1. Retrieve contexts for the original query.
    2. Evaluate retrieval quality.
    3. If GOOD: keep the original contexts, no rewrite.
    4. Else: rewrite the query ONCE and retrieve again.
    5. After corrective retrieval, inspect the second evaluation and select
       the best available evidence:

         - corrective GOOD ............ use corrective contexts.
         - corrective UNCERTAIN ........ use the stronger of the original and
                                         corrective contexts (by evaluation
                                         signals, never by recency).
          - corrective BAD ............. never use the bad corrective contexts;
                                          additionally, since the initial
                                          retrieval was already BAD, both
                                          attempts produced unusable evidence,
                                          so return empty (no trusted context).

       In every failure mode (rewrite failure, corrective retrieval failure,
       corrective evaluation failure, empty corrective retrieval) the original
       contexts are preserved, or empty if the original is also empty.

Hard limits (never exceeded in a single call):

    - at most 1 rewrite
    - at most 2 retrieval passes
    - at most 2 evaluations
    - no recursive CRAG calls

The orchestrator is provider-agnostic: it only depends on the retriever,
evaluator, and rewriter abstractions passed to it.  It never touches the
final answer prompt — the caller remains responsible for building the prompt
from the original question and the returned (possibly corrected / empty)
contexts.  When both attempts yield no usable evidence, the orchestrator
returns an empty list so the PromptBuilder can signal insufficient document
evidence rather than the system fabricating an answer.
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

# Quality ranking used when comparing the original and corrective evaluations.
_QUALITY_RANK = {
    RetrievalQuality.GOOD: 2,
    RetrievalQuality.UNCERTAIN: 1,
    RetrievalQuality.BAD: 0,
}


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
            The final selected contexts: the best available evidence among the
            original and corrective retrievals, chosen by retrieval quality and
            evaluator confidence.  Returns an empty list only when both attempts
            yield no usable evidence, so the caller can signal the absence of
            document evidence instead of fabricating an answer.
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
        initial_eval: RetrievalEvaluation = self._evaluator.evaluate(query, contexts)
        if initial_eval.quality is RetrievalQuality.GOOD:
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

        # Empty corrective retrieval is "nothing useful" → keep the original
        # (which may itself be empty, in which case the final result is empty).
        if not corrected:
            logger.info("CRAG corrective retrieval empty; using original contexts.")
            return contexts

        # Second evaluation (count: 2).
        try:
            corrected_eval: RetrievalEvaluation = self._evaluator.evaluate(
                rewritten, corrected
            )
        except Exception as exc:  # corrective evaluation failure → fall back
            logger.warning(
                "CRAG corrective evaluation failed; using original contexts: %s",
                exc,
            )
            return contexts

        # Final context selection driven by the corrective evaluation quality.
        if corrected_eval.quality is RetrievalQuality.GOOD:
            return corrected

        if corrected_eval.quality is RetrievalQuality.UNCERTAIN:
            # Use the genuinely better of the two evidenced candidates.  We do
            # NOT prefer the corrective retrieval merely because it is newer;
            # the decision is made purely from existing evaluation signals.
            if self._is_better(initial_eval, corrected_eval):
                return corrected
            return contexts

        # corrected_eval.quality is BAD and the initial was already BAD: both
        # retrieval attempts produced unusable evidence. Never present either
        # weak result as trusted document context — return empty so the caller
        # signals insufficient evidence instead of fabricating an answer.
        return []

    @staticmethod
    def _is_better(
        initial: RetrievalEvaluation,
        corrected: RetrievalEvaluation,
    ) -> bool:
        """Return True if *corrected* is the stronger evidence of the two.

        The decision uses only existing evaluation signals: a higher quality
        rank wins outright; ties are broken by the evaluator's confidence so we
        pick the genuinely stronger context rather than the newer one.

        Args:
            initial: The evaluation of the original retrieval.
            corrected: The evaluation of the corrective retrieval.

        Returns:
            True if the corrective evidence should be preferred.
        """
        corrected_rank = _QUALITY_RANK[corrected.quality]
        initial_rank = _QUALITY_RANK[initial.quality]
        if corrected_rank != initial_rank:
            return corrected_rank > initial_rank
        return corrected.confidence > initial.confidence
