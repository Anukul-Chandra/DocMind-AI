import logging

import httpx

from app.services.llm.providers.base import (
    APIError,
    AuthenticationError,
    BaseProvider,
    InvalidResponseError,
    ProviderError,
    RateLimitError,
    build_user_content,
)

logger = logging.getLogger(__name__)

#: Default Agnes AI OpenAI-compatible gateway base URL, taken from the official
#: Agnes AI documentation (https://agnes-ai.com/doc/overview). Overridable via
#: settings.agnes_base_url so alternate/regional routes can be configured
#: without code changes.
AGNES_DEFAULT_BASE_URL = "https://apihub.agnes-ai.com/v1"


class AgnesProvider(BaseProvider):
    """Agnes AI-backed LLM provider (OpenAI-compatible chat completions).

    Agnes exposes an OpenAI-style ``/v1/chat/completions`` endpoint authenticated
    with ``Authorization: Bearer <API key>``. This provider follows the same
    BaseProvider contract used by Gemini/Groq/OpenRouter and maps every failure
    onto the shared provider error types so ProviderManager failover works
    unchanged.

    Configuration is injected through the constructor so the provider has no
    direct dependency on the global settings object.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = AGNES_DEFAULT_BASE_URL,
        timeout: int = 60,
    ) -> None:
        """Initialize the provider with an API key, model, and base URL.

        Args:
            api_key: The Agnes API key (kept server-side only; never logged).
            model: The Agnes model identifier (e.g. ``agnes-2.5-flash``).
            base_url: The Agnes OpenAI-compatible base URL.
            timeout: HTTP client timeout in seconds.
        """
        if not api_key:
            raise ValueError("AgnesProvider requires an API key")
        if not model or not model.strip():
            raise ValueError("AgnesProvider requires a non-empty model id")
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout,
        )

    @property
    def model(self) -> str:
        """Return the configured Agnes model identifier."""
        return self._model

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
        images: list[dict] | None = None,
    ) -> str:
        """Generate a response using the configured Agnes model.

        Args:
            prompt: The user prompt (already built by ProviderManager-style
                callers).
            system_prompt: An optional system prompt guiding the model.
            temperature: Sampling temperature for the model.
            max_tokens: Maximum number of tokens to generate.
            images: Optional list of base64-encoded image dicts with keys
                ``mime`` and ``data``. Agnes supports image-URL content parts, so
                these are forwarded via ``build_user_content`` when present.

        Returns:
            The generated text from the model.

        Raises:
            ProviderError: If the request fails at the network level or times
                out.
            AuthenticationError: If the API key is rejected.
            RateLimitError: If Agnes rate limits the request.
            APIError: If Agnes returns another non-success HTTP response.
            InvalidResponseError: If the response cannot be parsed or contains
                no usable message content.
        """
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append(
            {"role": "user", "content": build_user_content(prompt, images)}
        )

        payload = {
            "model": self._model,
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
            raise ProviderError(f"Agnes request timed out: {exc}") from exc
        except httpx.ConnectError as exc:
            raise ProviderError(f"Agnes connection failed: {exc}") from exc
        except httpx.RequestError as exc:
            raise ProviderError(f"Agnes request failed: {exc}") from exc

        if response.status_code in (401, 403):
            raise AuthenticationError(
                "Agnes authentication failed; check your API key."
            )
        if response.status_code == 429:
            raise RateLimitError("Agnes rate limit exceeded.")
        if response.status_code != 200:
            raise APIError(
                f"Agnes returned HTTP {response.status_code}: {response.text}",
                status_code=response.status_code,
            )

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise InvalidResponseError(
                f"Invalid Agnes response: {exc}"
            ) from exc

        # Some models return null/empty content; treat that as invalid so
        # callers fail over instead of propagating empty text.
        if not isinstance(content, str) or not content.strip():
            raise InvalidResponseError(
                "Agnes returned an empty message content"
            )

        return content
