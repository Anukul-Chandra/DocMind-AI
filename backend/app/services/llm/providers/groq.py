from groq import AsyncGroq
from groq import (
    AuthenticationError as GroqSDKAuthenticationError,
    RateLimitError as GroqSDKRateLimitError,
)
from groq import APIStatusError, GroqError

from app.core.config import settings
from app.services.llm.providers.base import BaseProvider, RecoverableError


class GroqProviderError(RecoverableError):
    """Base exception for Groq provider failures."""


class GroqAuthenticationError(GroqProviderError):
    """Raised when Groq rejects the API key."""


class GroqRateLimitError(GroqProviderError):
    """Raised when Groq rate limits the request."""


class GroqAPIError(GroqProviderError):
    """Raised when the Groq API returns an error."""


class GroqInvalidResponseError(GroqProviderError):
    """Raised when the Groq response cannot be parsed."""


class GroqProvider(BaseProvider):
    """Groq-backed LLM provider."""

    def __init__(self) -> None:
        """Initialize the provider with an API key and model from settings."""
        self._api_key: str = settings.groq_api_key
        self._model: str = settings.groq_model
        self._client = AsyncGroq(api_key=self._api_key)

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> str:
        """Generate a response using the configured Groq model.

        Args:
            prompt: The user prompt to send to Groq.
            system_prompt: An optional system prompt guiding the model.
            temperature: Sampling temperature for the model.
            max_tokens: Maximum number of tokens to generate.

        Returns:
            The generated text from the model.

        Raises:
            GroqAuthenticationError: If the API key is rejected.
            GroqRateLimitError: If Groq rate limits the request.
            GroqAPIError: If the Groq API returns an error.
            GroqInvalidResponseError: If the response is invalid.
        """
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except GroqSDKAuthenticationError as exc:
            raise GroqAuthenticationError(
                "Groq authentication failed; check your API key."
            ) from exc
        except GroqSDKRateLimitError as exc:
            raise GroqRateLimitError(
                "Groq rate limit exceeded."
            ) from exc
        except APIStatusError as exc:
            raise GroqAPIError(f"Groq API error {exc.status_code}: {exc}") from exc
        except GroqError as exc:
            raise GroqAPIError(f"Groq request failed: {exc}") from exc

        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError) as exc:
            raise GroqInvalidResponseError(
                f"Invalid Groq response: {exc}"
            ) from exc

        if content is None:
            raise GroqInvalidResponseError(
                "Groq response contained no text."
            )

        return content
