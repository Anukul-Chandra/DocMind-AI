from groq import AsyncGroq
from groq import (
    AuthenticationError as GroqSDKAuthenticationError,
    RateLimitError as GroqSDKRateLimitError,
)
from groq import APIStatusError, GroqError

from app.services.llm.providers.base import (
    APIError,
    AuthenticationError,
    BaseProvider,
    InvalidResponseError,
    RateLimitError,
    build_user_content,
)


class GroqProvider(BaseProvider):
    """Groq-backed LLM provider.

    Configuration is injected through the constructor so the provider has no
    direct dependency on the global settings object.
    """

    def __init__(self, api_key: str, model: str) -> None:
        """Initialize the provider with an API key and model.

        Args:
            api_key: The Groq API key.
            model: The Groq model identifier.
        """
        self._api_key = api_key
        self._model = model
        self._client = AsyncGroq(api_key=self._api_key)

    @property
    def model(self) -> str:
        """Return the configured Groq model identifier.

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
        """Generate a response using the configured Groq model.

        Args:
            prompt: The user prompt to send to Groq.
            system_prompt: An optional system prompt guiding the model.
            temperature: Sampling temperature for the model.
            max_tokens: Maximum number of tokens to generate.

        Returns:
            The generated text from the model.

        Raises:
            AuthenticationError: If the API key is rejected.
            RateLimitError: If Groq rate limits the request.
            APIError: If the Groq API returns an error.
            InvalidResponseError: If the response is invalid.
        """
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": build_user_content(prompt, images)})

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except GroqSDKAuthenticationError as exc:
            raise AuthenticationError(
                "Groq authentication failed; check your API key."
            ) from exc
        except GroqSDKRateLimitError as exc:
            raise RateLimitError(
                "Groq rate limit exceeded."
            ) from exc
        except APIStatusError as exc:
            raise APIError(f"Groq API error {exc.status_code}: {exc}") from exc
        except GroqError as exc:
            raise APIError(f"Groq request failed: {exc}") from exc

        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError) as exc:
            raise InvalidResponseError(
                f"Invalid Groq response: {exc}"
            ) from exc

        if content is None:
            raise InvalidResponseError(
                "Groq response contained no text."
            )

        return content