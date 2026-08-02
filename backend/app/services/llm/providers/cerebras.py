from app.services.llm.providers.base import BaseProvider


class CerebrasProvider(BaseProvider):
    """Cerebras-backed LLM provider."""

    @property
    def model(self) -> str:
        """Return the provider name as a placeholder model identifier.

        Returns:
            The provider name.
        """
        return type(self).__name__

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> str:
        raise NotImplementedError("CerebrasProvider.generate is not implemented yet.")
