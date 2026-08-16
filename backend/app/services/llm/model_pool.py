from app.services.llm.model_catalog import curate_models


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
        model_ids: Candidate OpenRouter model ids.
        preferred: Model ids to place first, in preference order.

    Returns:
        The curated pool as an ordered, deduplicated list.
    """
    curated = curate_models(model_ids)
    preferred = preferred or []
    leading = [model_id for model_id in preferred if model_id in curated]
    trailing = [model_id for model_id in curated if model_id not in leading]
    return leading + trailing


class ModelPoolManager:
    """Manage a rotating pool of OpenRouter models."""

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
            raise RuntimeError("No available OpenRouter models.")
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
