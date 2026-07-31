import logging

from app.services.llm.providers.base import BaseProvider

logger = logging.getLogger(__name__)


class AllProvidersFailedError(Exception):
    """Raised when every provider fails to generate a response."""


class ProviderManager:
    """Try providers in priority order and return the first successful response."""

    def __init__(self, providers: list[BaseProvider]) -> None:
        if not providers:
            raise ValueError("providers must not be empty")
        self._providers: list[BaseProvider] = list(providers)

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> str:
        """Generate a response, falling back to the next provider on failure.

        Args:
            prompt: The user prompt to send to the provider.
            system_prompt: An optional system prompt guiding the provider.
            temperature: Sampling temperature for the provider.
            max_tokens: Maximum number of tokens to generate.

        Returns:
            The generated text from the first successful provider.

        Raises:
            AllProvidersFailedError: If all providers fail.
        """
        last_error: Exception | None = None
        for provider in self._providers:
            try:
                return await provider.generate(
                    prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Provider %s failed: %s", type(provider).__name__, exc
                )
        raise AllProvidersFailedError("All providers failed") from last_error
