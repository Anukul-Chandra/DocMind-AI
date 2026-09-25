"""Compatibility adapter for the extracted gateway provider manager."""

from typing import AsyncIterator

from app.models.llm import LLMResponse, LLMStreamChunk
from gateway.llm_gateway.contracts import LLMUnavailableError
from gateway.llm_gateway.provider_manager import (
    ProviderManager as GatewayProviderManager,
    _is_image_error,
    _is_image_error_response,
)


class ProviderManager(GatewayProviderManager):
    """Preserve the legacy DocMind response contract over the gateway manager."""

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
        images: list[dict] | None = None,
    ) -> LLMResponse:
        response = await super().generate(
            prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            images=images,
        )
        return LLMResponse.model_validate(response.model_dump())

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
        images: list[dict] | None = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        async for chunk in super().generate_stream(
            prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            images=images,
        ):
            yield chunk


__all__ = [
    "LLMUnavailableError",
    "ProviderManager",
    "_is_image_error",
    "_is_image_error_response",
]