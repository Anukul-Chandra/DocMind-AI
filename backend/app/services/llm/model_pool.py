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
