import json
import logging
from typing import AsyncIterator

import httpx

from app.services.llm.model_pool import ModelPoolManager
from app.services.llm.providers.base import (
    APIError,
    AuthenticationError,
    BaseProvider,
    InvalidResponseError,
    ProviderError,
    RateLimitError,
)

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

#: HTTP status codes treated as transient, model-specific failures. These are
#: the only APIError codes that trigger model rotation; everything else is
#: considered permanent and re-raised immediately.
_RECOVERABLE_STATUS_CODES: frozenset[int] = frozenset({404, 408, 429})


def _is_recoverable_error(exc: ProviderError) -> bool:
    """Decide whether an OpenRouter error is transient enough to rotate models.

    Only transient failures (rate limiting, temporary/server failures,
    timeouts, model unavailability) advance the model pool. Permanent
    authentication and configuration errors are re-raised without rotating.

    Args:
        exc: The provider error raised by a single model attempt.

    Returns:
        True if the error is recoverable on the next model, False otherwise.
    """
    if isinstance(exc, AuthenticationError):
        return False
    if isinstance(exc, RateLimitError):
        return True
    if isinstance(exc, InvalidResponseError):
        return False
    if isinstance(exc, APIError):
        if exc.status_code is None:
            return True
        return exc.status_code >= 500 or exc.status_code in _RECOVERABLE_STATUS_CODES
    return True


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
        """Generate a response, rotating through the pool on recoverable errors.

        The current model is tried first. If it fails with a transient,
        recoverable error (rate limit, temporary server failure, timeout, or
        model unavailability), the failure is recorded, ModelPoolManager is
        advanced, and the request is retried with the next model. Each
        available model is attempted at most once per request. If every model
        fails, the last ProviderError is re-raised so ProviderManager can fall
        back to the next provider. Non-recoverable errors (authentication,
        configuration) are re-raised immediately without rotating.

        Args:
            prompt: The user prompt to send to OpenRouter.
            system_prompt: An optional system prompt guiding the model.
            temperature: Sampling temperature for the model.
            max_tokens: Maximum number of tokens to generate.

        Returns:
            The generated text from the first model that succeeds.

        Raises:
            ProviderError: If the request fails at the network level or every
                model in the pool fails.
            AuthenticationError: If the API key is rejected.
            APIError: If OpenRouter returns a permanent HTTP error.
            InvalidResponseError: If the response is invalid.
        """
        last_error: ProviderError | None = None
        while True:
            model = self._model_pool.get_current_model()
            try:
                return await self._generate_once(
                    model,
                    prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except ProviderError as exc:
                last_error = exc
                if not _is_recoverable_error(exc):
                    logger.warning(
                        "OpenRouter model %s failed: %s", model, exc
                    )
                    raise
                logger.warning(
                    "OpenRouter model %s failed (recoverable); rotating: %s",
                    model,
                    exc,
                )
                try:
                    self._model_pool.move_next()
                except RuntimeError:
                    break

        if last_error is not None:
            logger.warning(
                "All OpenRouter models failed; handing off to next provider"
            )
            raise last_error
        raise ProviderError("No available OpenRouter models.")

    async def _generate_once(
        self,
        model: str,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> str:
        """Send a single request to OpenRouter using the given model.

        This performs exactly one HTTP attempt and does not rotate the pool;
        rotation is managed by the caller.

        Args:
            model: The model id to attempt.
            prompt: The user prompt to send to OpenRouter.
            system_prompt: An optional system prompt guiding the model.
            temperature: Sampling temperature for the model.
            max_tokens: Maximum number of tokens to generate.

        Returns:
            The generated text from the model.

        Raises:
            ProviderError: If the request fails at the network level.
            AuthenticationError: If the API key is rejected.
            RateLimitError: If OpenRouter rate limits the request.
            APIError: If OpenRouter returns a permanent HTTP error.
            InvalidResponseError: If the response is invalid.
        """
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
        if response.status_code == 429:
            raise RateLimitError(
                "OpenRouter rate limit exceeded."
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