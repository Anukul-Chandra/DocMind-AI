"""Model pool management for the reusable LLM gateway boundary."""

import logging
import re
from typing import FrozenSet

logger = logging.getLogger(__name__)

#: Exact name tokens that mark a model as unsuitable for general
#: conversational/RAG use: code-specialized variants, tiny-capacity tiers,
#: and embedding/reranker specialists.
UNSUITABLE_MODEL_TOKENS: FrozenSet[str] = frozenset(
    {
        "code",
        "coder",
        "coding",
        "mini",
        "tiny",
        "nano",
        "micro",
        "embed",
        "embedding",
        "rerank",
        "reranker",
    }
)

#: Separators used to split a model name into comparison tokens.
_MODEL_TOKEN_PATTERN = re.compile(r"[^a-zA-Z0-9]+")


def _model_slug(model_id: str) -> str:
    """Return the model-name portion of an id, without provider or suffix.

    Args:
        model_id: A model id (e.g. ``"cohere/north-mini-code:free"``).

    Returns:
        The model name (e.g. ``"north-mini-code"``).
    """
    name = model_id.split("/", 1)[-1]
    return name.split(":", 1)[0]


def curate_models(model_ids: list[str]) -> list[str]:
    """Filter a list of model ids down to general-purpose conversational models.

    Code-specialized, tiny-capacity (mini/tiny/nano/micro), and
    embedding/reranker models are excluded by matching exact tokens from the
    model name. Tokens are compared exactly so names like ``minimax-01`` are
    not misclassified by a ``mini`` substring.

    Args:
        model_ids: Model ids to curate.

    Returns:
        A new list containing only the suitable model ids, in input order.
    """
    return [
        model_id
        for model_id in model_ids
        if not (
            UNSUITABLE_MODEL_TOKENS
            & set(_MODEL_TOKEN_PATTERN.split(_model_slug(model_id)))
        )
    ]


def build_curated_pool(
    model_ids: list[str],
    preferred: list[str] | None = None,
) -> list[str]:
    """Build a curated model pool, ordering preferred models first.

    Unsuitable models (code/mini/tiny/embedding specialists) are excluded via
    :func:`curate_models`. The remaining models are deduplicated and ordered so
    that ``preferred`` models (trusted general-purpose defaults) lead the pool,
    ensuring capable models are tried first while the full curated set remains
    available for rotation.

    Args:
        model_ids: Candidate model ids.
        preferred: Model ids to place first, in preference order.

    Returns:
        The curated pool as an ordered, deduplicated list.
    """
    curated = curate_models(model_ids)
    preferred = preferred or []
    leading = [model_id for model_id in preferred if model_id in curated]
    trailing = [model_id for model_id in curated if model_id not in leading]
    return leading + trailing


class ModelCatalogError(Exception):
    """Raised when fetching models from a provider catalog fails."""


class NoFreeModelsError(ModelCatalogError):
    """Raised when a provider returns no free models."""


class ModelPoolManager:
    """Manage a rotating pool of models."""

    def __init__(self, models: list[str]) -> None:
        """Initialize the model pool with the given models.

        Args:
            models: The list of model ids to rotate through.

        Raises:
            ValueError: If the list of models is empty.
        """
        if not models:
            raise ValueError("models must not be empty")
        self._models: list[str] = list(models)
        self._current_index: int = 0

    def get_current_model(self) -> str:
        """Return the currently active model.

        Returns:
            The current model identifier.
        """
        return self._models[self._current_index]

    def move_next(self) -> str:
        """Move to the next model in the pool and return it.

        Returns:
            The next model identifier.

        Raises:
            RuntimeError: If no more models are available.
        """
        if self._current_index >= len(self._models) - 1:
            raise RuntimeError("No available models.")
        self._current_index += 1
        return self._models[self._current_index]

    def reset(self) -> None:
        """Reset the current index back to the first model."""
        self._current_index = 0

    def total_models(self) -> int:
        """Return the number of loaded models.

        Returns:
            The total count of models in the pool.
        """
        return len(self._models)