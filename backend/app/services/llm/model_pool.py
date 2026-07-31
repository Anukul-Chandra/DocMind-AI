from app.config.openrouter_models import OPENROUTER_MODELS


class ModelPoolManager:
    """Manage a rotating pool of OpenRouter models."""

    def __init__(self, models: list[str] | None = None) -> None:
        self._models: list[str] = models if models is not None else list(OPENROUTER_MODELS)
        self._index: int = 0

    def get_current_model(self) -> str:
        """Return the currently active model.

        Returns:
            The current model identifier.

        Raises:
            RuntimeError: If no models are available.
        """
        if not self._models:
            raise RuntimeError("No available OpenRouter models.")
        return self._models[self._index]

    def get_next_model(self) -> str:
        """Advance to and return the next model in the pool.

        Returns:
            The next model identifier.

        Raises:
            RuntimeError: If no models are available or the last model
                in the pool has already been reached.
        """
        if not self._models or self._index >= len(self._models) - 1:
            raise RuntimeError("No available OpenRouter models.")
        self._index += 1
        return self._models[self._index]

    def reset(self) -> None:
        """Reset the pool back to its first model."""
        self._index = 0

    def total_models(self) -> int:
        """Return the number of models in the pool.

        Returns:
            The total count of models.
        """
        return len(self._models)
