from abc import ABC, abstractmethod
from typing import AsyncIterator


class RecoverableError(Exception):
    """Base class for recoverable provider errors that allow failover."""


class BaseProvider(ABC):
    """Abstract interface for all LLM providers."""

    @property
    @abstractmethod
    def model(self) -> str:
        """Return the identifier of the model currently used by the provider.

        Returns:
            The current model identifier.
        """

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> str:
        """Generate a response for the given prompt.

        Args:
            prompt: The user prompt to send to the provider.
            system_prompt: An optional system prompt guiding the provider.
            temperature: Sampling temperature for the provider.
            max_tokens: Maximum number of tokens to generate.

        Returns:
            The generated text.
        """

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> AsyncIterator[str]:
        """Generate a streamed response for the given prompt.

        Providers that do not support native streaming inherit this default
        implementation, which streams the full response in a single chunk. This
        guarantees every provider can be streamed without breaking the API.

        Args:
            prompt: The user prompt to send to the provider.
            system_prompt: An optional system prompt guiding the provider.
            temperature: Sampling temperature for the provider.
            max_tokens: Maximum number of tokens to generate.

        Yields:
            The generated text, as one or more chunks.

        Raises:
            RecoverableError: If the provider fails.
        """
        text = await self.generate(
            prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        yield text
