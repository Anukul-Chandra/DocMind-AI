from app.models.llm import LLMResponse
from app.services.chat.models import ChatResponse
from app.services.llm.provider_manager import ProviderManager
from app.services.llm.prompt_builder import PromptBuilder
from app.services.vectorstore.retriever import Retriever


class ChatService:
    """Orchestrate document retrieval, prompt building, and LLM generation.

    This service is the composition root for a single chat turn. It depends only
    on the abstractions it receives (retriever, prompt builder, and provider
    manager) and knows nothing about concrete LLM providers such as OpenRouter,
    Gemini, or Groq.
    """

    def __init__(
        self,
        retriever: Retriever,
        prompt_builder: PromptBuilder,
        provider_manager: ProviderManager,
    ) -> None:
        """Initialize the chat service with its collaborators.

        Args:
            retriever: Retrieves relevant document chunks for a question.
            prompt_builder: Builds the prompt to send to the LLM.
            provider_manager: Generates an answer via the configured LLM provider.
        """
        self._retriever = retriever
        self._prompt_builder = prompt_builder
        self._provider_manager = provider_manager

    async def chat(self, question: str) -> ChatResponse:
        """Answer a question using retrieved document context.

        Args:
            question: The user's question.

        Returns:
            A chat response containing the LLM answer and provenance
            information (provider and model).
        """
        contexts = self._retriever.retrieve(question)
        prompt = self._prompt_builder.build_prompt(question, contexts)
        response: LLMResponse = await self._provider_manager.generate(prompt)
        return ChatResponse(
            answer=response.text,
            provider=response.provider,
            model=response.model,
        )