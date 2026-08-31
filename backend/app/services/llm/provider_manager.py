import logging
from typing import AsyncIterator

from app.models.llm import LLMResponse, LLMStreamChunk
from app.services.llm.providers.base import BaseProvider, RecoverableError

logger = logging.getLogger(__name__)


def _is_image_error(exc: Exception) -> bool:
    """Return True when a provider failure appears to be image-related."""
    message = str(exc).lower()
    return "image" in message or "vision" in message or "multimodal" in message


def _is_image_error_response(text: str) -> bool:
    """Return True when a 200-response content looks like an image-support error.

    Some providers (e.g. OpenRouter) return HTTP 200 with an error message in
    the ``content`` field instead of raising an exception. This detects those
    responses so the caller can retry text-only.
    """
    lowered = text.lower().strip()
    return (
        "does not support image" in lowered
        or "does not support vision" in lowered
        or "does not support multimodal" in lowered
    )


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
        images: list[dict] | None = None,
    ) -> LLMResponse:
        """Generate a response, failing over to the next provider on error.

        Args:
            prompt: The user prompt to send to the providers.
            system_prompt: An optional system prompt guiding the providers.
            temperature: Sampling temperature for the providers.
            max_tokens: Maximum number of tokens to generate.
            images: Optional list of base64-encoded image dicts with keys
                ``mime`` and ``data``. Forwarded to providers that support
                multimodal input; ignored by providers that do not.

        Returns:
            The first successful LLM response.

        Raises:
            LLMUnavailableError: If every provider fails.
        """
        self._errors = []
        for provider in self._providers:
            provider_name = type(provider).__name__
            logger.info("Trying %s...", provider_name)
            try:
                text = await provider.generate(
                    prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    images=images,
                )
                # Some providers return HTTP 200 with an error message in the
                # content field (e.g. "this model does not support image
                # input") instead of raising an exception. Convert that into a
                # RecoverableError so the text-only retry below applies.
                if images and _is_image_error_response(text):
                    raise RecoverableError(text)
                logger.info("Success: Provider = %s", provider_name)
                return LLMResponse(
                    text=text,
                    provider=provider_name,
                    model=provider.model,
                )
            except RecoverableError as exc:
                if images and _is_image_error(exc):
                    logger.info(
                        "Provider %s rejected images; retrying text-only",
                        provider_name,
                    )
                    try:
                        text = await provider.generate(
                            prompt,
                            system_prompt=system_prompt,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            images=None,
                        )
                        logger.info(
                            "Success: Provider = %s (text-only retry)",
                            provider_name,
                        )
                        return LLMResponse(
                            text=text,
                            provider=provider_name,
                            model=provider.model,
                        )
                    except RecoverableError:
                        pass
                self._errors.append((provider_name, exc))
                logger.warning(
                    "Provider %s failed: %s", provider_name, exc
                )
        raise LLMUnavailableError("All providers failed to generate a response.")

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
        images: list[dict] | None = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        """Stream a response, failing over to the next provider on error.

        Provider-agnostic: each provider is streamed in configured priority
        order. If a provider fails before yielding its first chunk, the next
        provider is tried. Once streaming begins, the chosen provider is kept.

        Args:
            prompt: The user prompt to send to the providers.
            system_prompt: An optional system prompt guiding the providers.
            temperature: Sampling temperature for the providers.
            max_tokens: Maximum number of tokens to generate.

        Yields:
            LLMStreamChunk objects tagging each fragment with its provider.

        Raises:
            LLMUnavailableError: If every provider fails before streaming.
        """
        self._errors = []
        for provider in self._providers:
            provider_name = type(provider).__name__
            logger.info("Trying stream %s...", provider_name)
            stream = provider.generate_stream(
                prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                images=images,
            )
            first_chunk = True
            try:
                async for fragment in stream:
                    yield LLMStreamChunk(
                        content=fragment,
                        provider=provider_name,
                        model=provider.model,
                    )
                    first_chunk = False
                logger.info("Success: Provider = %s", provider_name)
                return
            except RecoverableError as exc:
                self._errors.append((provider_name, exc))
                logger.warning(
                    "Provider %s failed streaming: %s", provider_name, exc
                )
                if not first_chunk:
                    raise
        raise LLMUnavailableError("All providers failed to generate a response.")
