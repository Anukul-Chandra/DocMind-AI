from abc import ABC, abstractmethod


class RecoverableError(Exception):
    """Base class for recoverable provider errors that allow failover."""


class BaseProvider(ABC):
    """Abstract interface for all LLM providers."""

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
