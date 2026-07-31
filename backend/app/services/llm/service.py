from app.services.llm.base import BaseLLM


class LLMService(BaseLLM):
    """Default LLM service until a provider is configured."""

    def generate(self, prompt: str) -> str:
        raise NotImplementedError("No LLM provider configured.")
