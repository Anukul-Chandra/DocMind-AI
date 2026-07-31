import httpx

from app.core.config import settings
from app.services.llm.model_pool import ModelPoolManager
from app.services.llm.providers.base import BaseProvider

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
CHAT_COMPLETIONS_URL = f"{OPENROUTER_BASE_URL}/chat/completions"


class OpenRouterError(Exception):
    """Base exception for OpenRouter provider failures."""


class OpenRouterRequestError(OpenRouterError):
    """Raised when the OpenRouter request fails at the network level."""


class OpenRouterAuthenticationError(OpenRouterError):
    """Raised when OpenRouter rejects the API key."""


class OpenRouterHTTPError(OpenRouterError):
    """Raised when OpenRouter returns an HTTP error."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        super().__init__(detail)


class OpenRouterInvalidResponseError(OpenRouterError):
    """Raised when the OpenRouter response cannot be parsed."""


class OpenRouterProvider(BaseProvider):
    """OpenRouter-backed LLM provider."""

    def __init__(self, model_pool: ModelPoolManager) -> None:
        """Initialize the provider with a model pool and API key from settings.

        Args:
            model_pool: The model pool providing the current model.
        """
        self._model_pool = model_pool
        self._api_key: str = settings.openrouter_api_key
        self._client = httpx.AsyncClient(
            base_url=OPENROUTER_BASE_URL,
            timeout=settings.timeout,
        )

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
            OpenRouterError: If the request fails.
            OpenRouterAuthenticationError: If the API key is rejected.
            OpenRouterHTTPError: If OpenRouter returns an HTTP error.
            OpenRouterInvalidResponseError: If the response is invalid.
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
            raise OpenRouterRequestError(f"OpenRouter request timed out: {exc}") from exc
        except httpx.ConnectError as exc:
            raise OpenRouterRequestError(f"OpenRouter connection failed: {exc}") from exc
        except httpx.RequestError as exc:
            raise OpenRouterRequestError(f"OpenRouter request failed: {exc}") from exc

        if response.status_code in (401, 403):
            raise OpenRouterAuthenticationError(
                "OpenRouter authentication failed; check your API key."
            )
        if response.status_code != 200:
            raise OpenRouterHTTPError(
                response.status_code,
                f"OpenRouter returned HTTP {response.status_code}: {response.text}",
            )

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise OpenRouterInvalidResponseError(
                f"Invalid OpenRouter response: {exc}"
            ) from exc

        return content
