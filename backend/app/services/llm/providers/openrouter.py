import json
from typing import AsyncIterator

import httpx

from app.services.llm.model_pool import ModelPoolManager
from app.services.llm.providers.base import (
    APIError,
    AuthenticationError,
    BaseProvider,
    InvalidResponseError,
    ProviderError,
)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterProvider(BaseProvider):
    """OpenRouter-backed LLM provider.

    Configuration is injected through the constructor so the provider has no
    direct dependency on the global settings object.
    """

    def __init__(
        self,
        model_pool: ModelPoolManager,
        api_key: str,
        timeout: int = 60,
    ) -> None:
        """Initialize the provider with a model pool, API key, and timeout.

        Args:
            model_pool: The model pool providing the current model.
            api_key: The OpenRouter API key.
            timeout: Request timeout in seconds.
        """
        self._model_pool = model_pool
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=OPENROUTER_BASE_URL,
            timeout=timeout,
        )

    @property
    def model(self) -> str:
        """Return the current OpenRouter model from the pool.

        Returns:
            The current model identifier.
        """
        return self._model_pool.get_current_model()

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> str:
        """Generate a response using the current model from the pool.

        Args:
            prompt: The user prompt to send to OpenRouter.
            system_prompt: An optional system prompt guiding the model.
            temperature: Sampling temperature for the model.
            max_tokens: Maximum number of tokens to generate.

        Returns:
            The generated text from the model.

        Raises:
            ProviderError: If the request fails at the network level.
            AuthenticationError: If the API key is rejected.
            APIError: If OpenRouter returns an HTTP error.
            InvalidResponseError: If the response is invalid.
        """
        model = self._model_pool.get_current_model()

        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = await self._client.post(
                "/chat/completions",
                headers=headers,
                json=payload,
            )
        except httpx.TimeoutException as exc:
            raise ProviderError(f"OpenRouter request timed out: {exc}") from exc
        except httpx.ConnectError as exc:
            raise ProviderError(f"OpenRouter connection failed: {exc}") from exc
        except httpx.RequestError as exc:
            raise ProviderError(f"OpenRouter request failed: {exc}") from exc

        if response.status_code in (401, 403):
            raise AuthenticationError(
                "OpenRouter authentication failed; check your API key."
            )
        if response.status_code != 200:
            raise APIError(
                f"OpenRouter returned HTTP {response.status_code}: {response.text}",
                status_code=response.status_code,
            )

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise InvalidResponseError(
                f"Invalid OpenRouter response: {exc}"
            ) from exc

        return content

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> AsyncIterator[str]:
        """Stream a response using OpenRouter's server-side events.

        Args:
            prompt: The user prompt to send to OpenRouter.
            system_prompt: An optional system prompt guiding the model.
            temperature: Sampling temperature for the model.
            max_tokens: Maximum number of tokens to generate.

        Yields:
            Text fragments as they arrive from OpenRouter.

        Raises:
            AuthenticationError: If the API key is rejected.
            APIError: If OpenRouter returns an HTTP error.
        """
        model = self._model_pool.get_current_model()

        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with self._client.stream(
                "POST",
                "/chat/completions",
                headers=headers,
                json=payload,
            ) as response:
                if response.status_code in (401, 403):
                    raise AuthenticationError(
                        "OpenRouter authentication failed; check your API key."
                    )
                if response.status_code != 200:
                    await response.aread()
                    raise APIError(
                        f"OpenRouter returned HTTP {response.status_code}: {response.text}",
                        status_code=response.status_code,
                    )
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[len("data: ") :].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0]["delta"]
                        content = delta.get("content", "")
                    except (ValueError, KeyError, IndexError, TypeError):
                        continue
                    if content:
                        yield content
        except httpx.TimeoutException as exc:
            raise ProviderError(f"OpenRouter stream timed out: {exc}") from exc
        except httpx.ConnectError as exc:
            raise ProviderError(f"OpenRouter connection failed: {exc}") from exc
        except httpx.RequestError as exc:
            raise ProviderError(f"OpenRouter stream request failed: {exc}") from exc