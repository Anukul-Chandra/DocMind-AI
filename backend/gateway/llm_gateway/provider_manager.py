"""Provider failover manager for the reusable LLM gateway boundary."""

import logging
import time
from typing import AsyncIterator

from gateway.llm_gateway.contracts import (
    BaseProvider,
    LLMResponse,
    LLMStreamChunk,
    LLMUnavailableError,
    RecoverableError,
)

logger = logging.getLogger(__name__)


def _is_image_error(exc: Exception) -> bool:
    """Return True when a provider failure appears to be image-related."""
    message = str(exc).lower()
    return "image" in message or "vision" in message or "multimodal" in message


def _is_image_error_response(text: str) -> bool:
    """Return True when a successful response contains an image error."""
    lowered = text.lower().strip()
    return (
        "does not support image" in lowered
        or "does not support vision" in lowered
        or "does not support multimodal" in lowered
    )


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
        """Generate a response, failing over to the next provider on error."""
        self._errors = []
        _t_total = time.perf_counter()
        for provider in self._providers:
            provider_name = type(provider).__name__
            logger.info("Trying %s...", provider_name)
            try:
                _t_att = time.perf_counter()
                text = await provider.generate(
                    prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    images=images,
                )
                if images and _is_image_error_response(text):
                    raise RecoverableError(text)
                _t_elapsed = time.perf_counter() - _t_att
                logger.info("Success: Provider = %s in %.3fs", provider_name, _t_elapsed)
                return LLMResponse(
                    text=text,
                    provider=provider_name,
                    model=provider.model,
                )
            except RecoverableError as exc:
                _t_elapsed = time.perf_counter() - _t_att
                if images and _is_image_error(exc):
                    logger.info(
                        "Provider %s rejected images after %.3fs; retrying text-only",
                        provider_name,
                        _t_elapsed,
                    )
                    try:
                        _t_att = time.perf_counter()
                        text = await provider.generate(
                            prompt,
                            system_prompt=system_prompt,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            images=None,
                        )
                        _t_retry = time.perf_counter() - _t_att
                        logger.info(
                            "Success: Provider = %s (text-only retry) in %.3fs",
                            provider_name,
                            _t_retry,
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
                    "Provider %s failed after %.3fs: %s",
                    provider_name,
                    _t_elapsed,
                    exc,
                )
        logger.info(
            "All providers failed; total failover time %.3fs",
            time.perf_counter() - _t_total,
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
        """Stream a response, failing over before the first chunk."""
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
                logger.warning("Provider %s failed streaming: %s", provider_name, exc)
                if not first_chunk:
                    raise
        raise LLMUnavailableError("All providers failed to generate a response.")