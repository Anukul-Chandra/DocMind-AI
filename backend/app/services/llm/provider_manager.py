import logging

from app.models.llm import LLMResponse
from app.services.llm.providers.base import BaseProvider, RecoverableError

logger = logging.getLogger(__name__)


class LLMUnavailableError(Exception):
    """Raised when all providers fail to generate a response."""


class ProviderManager:
    """Coordinate multiple LLM providers with automatic failover."""

    def __init__(self, providers: list[BaseProvider]) -> None:
        if not providers:
            raise ValueError("providers must not be empty")
        self._providers: list[BaseProvider] = list(providers)
        self._errors: list[tuple[str, Exception]] = []

    @property
    def errors(self) -> list[tuple[str, Exception]]:
        """Return the list of provider errors recorded during the last call."""
        return list(self._errors)

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> LLMResponse:
        """Generate a response, failing over to the next provider on error.

        Args:
            prompt: The user prompt to send to the providers.
            system_prompt: An optional system prompt guiding the providers.
            temperature: Sampling temperature for the providers.
            max_tokens: Maximum number of tokens to generate.

        Returns:
            The first successful LLM response.

        Raises:
            LLMUnavailableError: If every provider fails.
        """
        self._errors = []
        for provider in self._providers:
            try:
                text = await provider.generate(
                    prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return LLMResponse(text=text, provider=type(provider).__name__)
            except RecoverableError as exc:
                self._errors.append((type(provider).__name__, exc))
                logger.warning(
                    "Provider %s failed: %s", type(provider).__name__, exc
                )
        raise LLMUnavailableError("All providers failed to generate a response.")
