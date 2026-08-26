from google import genai
from google.genai import errors, types
from httpx import ConnectError, TimeoutException

from app.services.llm.providers.base import (
    APIError,
    AuthenticationError,
    BaseProvider,
    InvalidResponseError,
    ProviderError,
    RateLimitError,
)


class GeminiProvider(BaseProvider):
    """Google Gemini-backed LLM provider.

    Configuration is injected through the constructor so the provider has no
    direct dependency on the global settings object.
    """

    def __init__(self, api_key: str, model: str) -> None:
        """Initialize the provider with an API key and model.

        Args:
            api_key: The Gemini API key.
            model: The Gemini model identifier.
        """
        self._api_key = api_key
        self._model = model
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
        images: list[dict] | None = None,
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
            AuthenticationError: If the API key is rejected.
            RateLimitError: If Gemini rate limits the request.
            APIError: If the Gemini API returns an error.
            ProviderError: If the request fails at the network layer.
            InvalidResponseError: If the response is invalid.
        """
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            max_output_tokens=max_tokens,
        )

        # Build multimodal contents when images are present
        if images:
            parts: list[types.Part] = [types.Part(text=prompt)]
            for img in images:
                parts.append(types.Part(
                    inline_data=types.Blob(
                        mime_type=img["mime"],
                        data=img["data"],
                    ),
                ))
            contents = parts
        else:
            contents = prompt

        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=contents,
                config=config,
            )
        except errors.ClientError as exc:
            if exc.code in (400, 401, 403):
                raise AuthenticationError(
                    "Gemini authentication failed; check your API key."
                ) from exc
            if exc.code == 429:
                raise RateLimitError(
                    "Gemini rate limit exceeded."
                ) from exc
            raise APIError(f"Gemini API error {exc.code}: {exc}") from exc
        except errors.ServerError as exc:
            raise APIError(f"Gemini server error {exc.code}: {exc}") from exc
        except errors.APIError as exc:
            raise APIError(f"Gemini API error {exc.code}: {exc}") from exc
        except (TimeoutException, ConnectError) as exc:
            raise ProviderError(
                f"Gemini request failed at the network layer: {exc}"
            ) from exc

        content = response.text
        if content is None:
            raise InvalidResponseError(
                "Gemini response contained no text."
            )

        return content