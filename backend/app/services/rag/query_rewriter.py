"""Rewrite vague user queries into retrieval-optimized search queries.

The QueryRewriter transforms a user's natural-language question into a
short, keyword-rich query that maximizes retrieval recall.  It does **not**
answer the question — it only produces a better search query.

The rewrite is performed via the existing ``ProviderManager.generate()``
infrastructure, keeping the rewriter provider-agnostic.  A dedicated
system prompt constrains the LLM to rewriting-only behaviour.

Safety properties:
    - On provider failure the original query is returned unchanged.
    - On empty or invalid provider output the original query is returned.
    - A hard maximum output length prevents runaway generation.
    - The rewriter is non-recursive by construction (it never calls itself),
      so at most one rewrite occurs per ``rewrite()`` invocation.  Enforcing
      "one rewrite per CRAG cycle" at the orchestration level is the caller's
      responsibility when this is later integrated.
"""

from __future__ import annotations

import logging

from app.models.llm import LLMResponse
from app.services.llm.provider_manager import (
    LLMUnavailableError,
    ProviderManager,
)

logger = logging.getLogger(__name__)

_REWRITE_SYSTEM_PROMPT = (
    "You are a retrieval query optimizer. "
    "Rewrite the user's question into a concise search query. "
    "Do not answer the question. "
    "Do not invent information. "
    "Preserve names, entities and important terms. "
    "Return only the rewritten query."
)

_DEFAULT_MAX_OUTPUT_LENGTH = 200


class QueryRewriter:
    """Rewrite a user query into a retrieval-optimized search query.

    Args:
        provider_manager: The shared ``ProviderManager`` used for LLM calls.
        max_output_length: Hard cap on the rewritten query length (characters).
            Strings exceeding this limit are rejected and the original query
            is returned instead.
    """

    def __init__(
        self,
        provider_manager: ProviderManager,
        max_output_length: int = _DEFAULT_MAX_OUTPUT_LENGTH,
    ) -> None:
        self._provider_manager = provider_manager
        self._max_output_length = max_output_length

    async def rewrite(self, query: str) -> str:
        """Rewrite *query* into a retrieval-optimized search query.

        The method is safe to call in all failure modes:
            - Provider raises → original query returned.
            - Provider returns empty / whitespace → original query returned.
            - Provider output exceeds ``max_output_length`` → original query
              returned.

        Args:
            query: The original user question.

        Returns:
            A retrieval-optimized rewrite of *query*, or *query* unchanged
            if rewriting failed or was unsafe.
        """
        if not query or not query.strip():
            return query

        try:
            response: LLMResponse = await self._provider_manager.generate(
                prompt=query,
                system_prompt=_REWRITE_SYSTEM_PROMPT,
                temperature=0.0,
                max_tokens=60,
            )
        except (LLMUnavailableError, Exception) as exc:
            logger.warning("QueryRewriter provider call failed: %s", exc)
            return query

        rewritten = _normalise(response.text)

        if not rewritten:
            logger.warning("QueryRewriter returned empty text; using original.")
            return query

        if len(rewritten) > self._max_output_length:
            logger.warning(
                "QueryRewriter output exceeds %d chars; using original.",
                self._max_output_length,
            )
            return query

        return rewritten


def _normalise(text: str) -> str:
    """Strip whitespace and collapse internal runs of spaces."""
    return " ".join(text.split()).strip()
