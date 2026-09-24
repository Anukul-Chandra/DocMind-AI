"""Provider-independent contracts for the reusable LLM gateway boundary."""

from abc import ABC, abstractmethod
from typing import AsyncIterator

from pydantic import BaseModel


def build_user_content(
    prompt: str, images: list[dict] | None = None
) -> str | list[dict]:
    """Build an OpenAI-compatible text or multimodal user content value."""
    if not images:
        return prompt
    parts: list[dict] = [{"type": "text", "text": prompt}]
    for image in images:
        parts.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{image['mime']};base64,{image['data']}",
                },
            }
        )
    return parts


class ProviderError(Exception):
    """Base class for provider failures eligible for gateway handling."""


class AuthenticationError(ProviderError):
    """Raised when a provider rejects its credentials."""


class RateLimitError(ProviderError):
    """Raised when a provider rate-limits a request."""


class APIError(ProviderError):
    """Raised for a non-success provider response."""

    def __init__(self, detail: str, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(detail)


class InvalidResponseError(ProviderError):
    """Raised when a provider response cannot be parsed."""


RecoverableError = ProviderError


class LLMUnavailableError(Exception):
    """Raised when all configured providers fail to generate a response."""


class BaseProvider(ABC):
    """Provider contract used by the existing provider and rotation layers."""

    @property
    @abstractmethod
    def model(self) -> str:
        """Return the current provider model identifier."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
        images: list[dict] | None = None,
    ) -> str:
        """Generate text for a prompt, optionally with image inputs."""

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
        images: list[dict] | None = None,
    ) -> AsyncIterator[str]:
        """Yield the complete non-streaming result as one fallback chunk."""
        text = await self.generate(
            prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            images=images,
        )
        yield text


class LLMResponse(BaseModel):
    """Generic text response returned by a gateway provider manager."""

    text: str
    provider: str
    model: str = ""


class LLMStreamChunk(BaseModel):
    """Generic streamed response chunk."""

    content: str
    provider: str
    model: str = ""