from app.services.llm.providers.base import BaseProvider


class GitHubModelsProvider(BaseProvider):
    """GitHub Models-backed LLM provider."""

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> str:
        raise NotImplementedError("GitHubModelsProvider.generate is not implemented yet.")
