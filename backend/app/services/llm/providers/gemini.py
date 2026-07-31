from app.services.llm.providers.base import BaseProvider


class GeminiProvider(BaseProvider):
    """Google Gemini-backed LLM provider."""

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> str:
        raise NotImplementedError("GeminiProvider.generate is not implemented yet.")
