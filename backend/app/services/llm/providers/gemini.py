from google import genai
from google.genai import errors, types

from app.core.config import settings
from app.services.llm.providers.base import BaseProvider, RecoverableError


class GeminiError(RecoverableError):
    """Base exception for Gemini provider failures."""


class GeminiAuthenticationError(GeminiError):
    """Raised when Gemini rejects the API key."""


class GeminiRateLimitError(GeminiError):
    """Raised when Gemini rate limits the request."""


class GeminiAPIError(GeminiError):
    """Raised when the Gemini API returns an error."""


class GeminiInvalidResponseError(GeminiError):
    """Raised when the Gemini response cannot be parsed."""


class GeminiProvider(BaseProvider):
    """Google Gemini-backed LLM provider."""

    def __init__(self) -> None:
        """Initialize the provider with an API key and model from settings."""
        self._api_key: str = settings.gemini_api_key
        self._model: str = settings.gemini_model
        self._client = genai.Client(api_key=self._api_key)

    @property
    def model(self) -> str:
        """Return the configured Gemini model identifier.

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
    ) -> str:
        """Generate a response using the configured Gemini model.

        Args:
            prompt: The user prompt to send to Gemini.
            system_prompt: An optional system prompt guiding the model.
            temperature: Sampling temperature for the model.
            max_tokens: Maximum number of tokens to generate.

        Returns:
            The generated text from the model.

        Raises:
            GeminiError: If the request fails.
            GeminiAuthenticationError: If the API key is rejected.
            GeminiRateLimitError: If Gemini rate limits the request.
            GeminiAPIError: If the Gemini API returns an error.
            GeminiInvalidResponseError: If the response is invalid.
        """
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            max_output_tokens=max_tokens,
        )

        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=prompt,
                config=config,
            )
        except errors.ClientError as exc:
            if exc.code in (400, 401, 403):
                raise GeminiAuthenticationError(
                    "Gemini authentication failed; check your API key."
                ) from exc
            if exc.code == 429:
                raise GeminiRateLimitError(
                    "Gemini rate limit exceeded."
                ) from exc
            raise GeminiAPIError(f"Gemini API error {exc.code}: {exc}") from exc
        except errors.ServerError as exc:
            raise GeminiAPIError(f"Gemini server error {exc.code}: {exc}") from exc
        except errors.APIError as exc:
            raise GeminiAPIError(f"Gemini API error {exc.code}: {exc}") from exc
        except Exception as exc:
            raise GeminiError(f"Gemini request failed: {exc}") from exc

        content = response.text
        if content is None:
            raise GeminiInvalidResponseError(
                "Gemini response contained no text."
            )

        return content
