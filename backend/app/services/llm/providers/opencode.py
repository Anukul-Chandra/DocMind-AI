import logging

import httpx

from app.services.llm.providers.base import (
    APIError,
    AuthenticationError,
    BaseProvider,
    InvalidResponseError,
    RateLimitError,
    ProviderError,
    build_user_content,
)

logger = logging.getLogger(__name__)

OPENCODE_BASE_URL = "https://opencode.ai/inference/openai/v1"


async def request_completion(
    client,
    model_id: str,
    prompt: str,
    system_prompt: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 1000,
    images: list[dict] | None = None,
) -> str:
    """Send one OpenAI-compatible chat completion request to OpenCode.

    Performs exactly one HTTP attempt for the given model id and maps
    failures onto the shared provider error types. Used by both the
    single-model provider and the rotating runtime layer.

    Args:
        client: An httpx-compatible async client bound to the OpenCode
            inference base URL.
        model_id: The OpenCode model identifier to request.
        prompt: The user prompt (already built by ProviderManager-style
            callers).
        system_prompt: An optional system prompt guiding the model.
        temperature: Sampling temperature for the model.
        max_tokens: Maximum number of tokens to generate.

    Returns:
        The generated text from the model.

    Raises:
        ProviderError: If the request fails at the network level or times
            out.
        AuthenticationError: If the endpoint rejects the request as
            unauthorized.
        RateLimitError: If OpenCode rate limits the request.
        APIError: If OpenCode returns another non-success HTTP response.
        InvalidResponseError: If the response cannot be parsed or does not
            contain usable message content.
    """
    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": build_user_content(prompt, images)})

    payload = {
        "model": model_id,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    try:
        response = await client.post(
            "/chat/completions",
            json=payload,
        )
    except httpx.TimeoutException as exc:
        raise ProviderError(f"OpenCode request timed out: {exc}") from exc
    except httpx.ConnectError as exc:
        raise ProviderError(f"OpenCode connection failed: {exc}") from exc
    except httpx.RequestError as exc:
        raise ProviderError(f"OpenCode request failed: {exc}") from exc

    if response.status_code in (401, 403):
        raise AuthenticationError(
            "OpenCode authentication failed; the request was rejected."
        )
    if response.status_code == 429:
        raise RateLimitError("OpenCode rate limit exceeded.")
    if response.status_code != 200:
        raise APIError(
            f"OpenCode returned HTTP {response.status_code}: {response.text}",
            status_code=response.status_code,
        )

    try:
        data = response.json()
        content = data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise InvalidResponseError(
            f"Invalid OpenCode response: {exc}"
        ) from exc

    # Some models return null/empty content; treat that as invalid so
    # callers fail over instead of propagating empty text.
    if not isinstance(content, str) or not content.strip():
        raise InvalidResponseError(
            "OpenCode returned an empty message content"
        )

    return content


class OpenCodeProvider(BaseProvider):
    """OpenCode-backed LLM provider for a single, dynamically supplied model.

    The free OpenCode inference endpoint is OpenAI-compatible and currently
    works without an Authorization header, so no credentials are handled
    here. The model id is injected by the caller (typically discovered via
    :class:`OpenCodeModelCatalogService`); nothing is hardcoded. Pooling,
    rotation, and cooldown handling are intentionally out of scope for this
    step.
    """

    def __init__(
        self,
        model: str,
        timeout: int = 60,
        base_url: str = OPENCODE_BASE_URL,
    ) -> None:
        """Initialize the provider with a model id and HTTP timeout.

        Args:
            model: The OpenCode model identifier to request.
            timeout: HTTP client timeout in seconds.
            base_url: The OpenAI-compatible OpenCode inference base URL.
        """
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must be a non-empty string")
        self._model = model
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
        )

    @property
    def model(self) -> str:
        """Return the configured OpenCode model identifier.

        Returns:
            The current model identifier.
        """
        return self._model

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
        images: list[dict] | None = None,
    ) -> str:
        """Generate a response using the configured OpenCode model.

        Args:
            prompt: The user prompt to send to OpenCode (already built by
                ProviderManager-style callers).
            system_prompt: An optional system prompt guiding the model.
            temperature: Sampling temperature for the model.
            max_tokens: Maximum number of tokens to generate.

        Returns:
            The generated text from the model.

        Raises:
            ProviderError: If the request fails at the network level or
                times out.
            AuthenticationError: If the endpoint rejects the request as
                unauthorized.
            RateLimitError: If OpenCode rate limits the request.
            APIError: If OpenCode returns another non-success HTTP response.
            InvalidResponseError: If the response cannot be parsed or does
                not contain usable message content.
        """
        return await request_completion(
            self._client,
            self._model,
            prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            images=images,
        )
