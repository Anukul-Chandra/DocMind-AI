from app.models.llm import LLMResponse
from app.services.llm.provider_manager import ProviderManager
from app.services.llm.prompt_builder import PromptBuilder
from app.services.vectorstore.retriever import Retriever


class ChatService:
    """Orchestrate retrieval, prompt building, and LLM generation."""

    def __init__(
        self,
        retriever: Retriever,
        prompt_builder: PromptBuilder,
        provider_manager: ProviderManager,
    ) -> None:
        self._retriever = retriever
        self._prompt_builder = prompt_builder
        self._provider_manager = provider_manager

    async def chat(self, question: str) -> LLMResponse:
        """Answer a question using retrieved document context.

        Args:
            question: The user's question.

        Returns:
            The LLM response generated from the retrieved context.
        """
        contexts = self._retriever.retrieve(question)
        prompt = self._prompt_builder.build_prompt(question, contexts)
        return await self._provider_manager.generate(prompt)
