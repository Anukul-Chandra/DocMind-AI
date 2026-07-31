import logging

from app.services.llm.model_pool import ModelPoolManager
from app.services.llm.providers.openrouter import (
    OpenRouterError,
    OpenRouterHTTPError,
    OpenRouterProvider,
    OpenRouterRequestError,
)

logger = logging.getLogger(__name__)

RETRYABLE_HTTP_STATUS_CODES = {429, 500, 502, 503}


class OpenRouterExhaustedError(OpenRouterError):
    """Raised when all OpenRouter models have been exhausted."""


class OpenRouterExecutor:
    """Execute OpenRouter calls with automatic model rotation."""

    def __init__(
        self,
        model_pool: ModelPoolManager,
        provider: OpenRouterProvider,
    ) -> None:
        self._model_pool = model_pool
        self._provider = provider

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> str:
        """Generate a response, rotating to the next model on retryable failures.

        Args:
            prompt: The user prompt to send to OpenRouter.
            system_prompt: An optional system prompt guiding the model.
            temperature: Sampling temperature for the model.
            max_tokens: Maximum number of tokens to generate.

        Returns:
            The generated text from the first successful model.

        Raises:
            OpenRouterExhaustedError: If all models fail or are exhausted.
        """
        while True:
            try:
                return await self._provider.generate(
                    prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except OpenRouterRequestError as exc:
                logger.warning(
                    "OpenRouter request failed for %s: %s",
                    self._model_pool.get_current_model(),
                    exc,
                )
            except OpenRouterHTTPError as exc:
                if exc.status_code not in RETRYABLE_HTTP_STATUS_CODES:
                    raise
                logger.warning(
                    "OpenRouter HTTP %d failed for %s",
                    exc.status_code,
                    self._model_pool.get_current_model(),
                )

            try:
                self._model_pool.move_next()
            except RuntimeError as exc:
                raise OpenRouterExhaustedError(
                    "All OpenRouter models have been exhausted."
                ) from exc
