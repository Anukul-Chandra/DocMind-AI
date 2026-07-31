from openai import OpenAI

from app.services.llm.base import BaseLLM


class OpenAIProvider(BaseLLM):
    """OpenAI-backed LLM provider."""

    def __init__(self, api_key: str, model: str) -> None:
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def generate(self, prompt: str) -> str:
        """Generate a response for the given prompt.

        Args:
            prompt: The prompt to send to the model.

        Returns:
            The generated text.

        Raises:
            Exception: If the OpenAI API request fails.
        """
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            raise Exception(f"OpenAI request failed: {exc}") from exc
        return response.choices[0].message.content
