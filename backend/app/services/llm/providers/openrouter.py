from app.services.llm.providers.base import BaseProvider


class OpenRouterProvider(BaseProvider):
    """OpenRouter-backed LLM provider."""

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> str:
        raise NotImplementedError("OpenRouterProvider.generate is not implemented yet.")
