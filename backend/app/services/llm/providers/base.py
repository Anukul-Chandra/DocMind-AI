from abc import ABC, abstractmethod
from typing import AsyncIterator


def build_user_content(
    prompt: str, images: list[dict] | None = None
) -> str | list[dict]:
    """Build a user message content field, attaching images when present.

    When ``images`` is empty or None, returns a plain string (backwards
    compatible with text-only providers).  When images are provided, returns
    a list of content parts following the OpenAI multimodal format.

    Args:
        prompt: The text prompt.
        images: Optional list of dicts with keys ``mime`` (MIME type string)
            and ``data`` (base64-encoded image bytes).

    Returns:
        A plain string when no images, or a list of content part dicts.
    """
    if not images:
        return prompt
    parts: list[dict] = [{"type": "text", "text": prompt}]
    for img in images:
        parts.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{img['mime']};base64,{img['data']}",
            },
        })
    return parts


class ProviderError(Exception):
    """Base class for recoverable provider errors that allow failover.

    All provider-specific failures subclass this so that ProviderManager can
    fail over to the next provider. Programming errors must not subclass it.
    """


class AuthenticationError(ProviderError):
    """Raised when a provider rejects the supplied API credentials."""


class RateLimitError(ProviderError):
    """Raised when a provider rate limits the request."""


class APIError(ProviderError):
    """Raised when a provider returns a non-success HTTP API response.

    Attributes:
        status_code: The HTTP status code returned by the provider, if known.
    """

    def __init__(self, detail: str, status_code: int | None = None) -> None:
        """Initialize the API error.

        Args:
            detail: A human-readable description of the failure.
            status_code: The HTTP status code from the provider, if known.
        """
        self.status_code = status_code
        super().__init__(detail)


class InvalidResponseError(ProviderError):
    """Raised when a provider response cannot be parsed."""


#: Backward-compatible alias retained so ProviderManager failover keeps working.
RecoverableError = ProviderError


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
        images: list[dict] | None = None,
    ) -> str:
        """Generate a response for the given prompt.

        Args:
            prompt: The user prompt to send to the provider.
            system_prompt: An optional system prompt guiding the provider.
            temperature: Sampling temperature for the provider.
            max_tokens: Maximum number of tokens to generate.
            images: Optional list of base64-encoded image dicts with keys
                ``mime`` and ``data``. Providers that support vision should
                include these as multimodal content parts.

        Returns:
            The generated text.

        Raises:
            ProviderError: If the provider fails (recoverable).
        """

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
        images: list[dict] | None = None,
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
            images: Optional list of base64-encoded image dicts.

        Yields:
            The generated text, as one or more chunks.

        Raises:
            ProviderError: If the provider fails.
        """
        text = await self.generate(
            prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            images=images,
        )
        yield text