from app.models.llm import LLMResponse
from app.services.llm.prompt_builder import PromptBuilder
from app.services.llm.provider_manager import ProviderManager
from app.services.retrieval.base import Retriever


class ChatService:
    """Orchestrate retrieval, prompt construction, and LLM generation.

    This service is the composition root for a single RAG chat turn. It
    retrieves the most relevant document chunks, builds the final prompt, and
    asks the configured LLM provider for an answer.

    It depends only on the ``Retriever``, ``PromptBuilder``, and
    ``ProviderManager`` abstractions it receives, and knows nothing about
    concrete providers such as OpenRouter, Gemini, or Groq.
    """

    def __init__(
        self,
        retriever: Retriever,
        prompt_builder: PromptBuilder,
        provider_manager: ProviderManager,
    ) -> None:
        """Initialize the chat service with its collaborators.

        Args:
            retriever: Retrieves the most relevant document chunks for a
                question.
            prompt_builder: Builds the final prompt from the question and the
                retrieved chunks.
            provider_manager: Generates the answer via the configured LLM
                provider.
        """
        self._retriever = retriever
        self._prompt_builder = prompt_builder
        self._provider_manager = provider_manager

    async def chat(self, question: str, owner_id: str = "") -> LLMResponse:
        """Answer a question using the retrieved owner-scoped document context.

        The caller (the API layer) is responsible for authentication and for
        passing the authenticated user's ``owner_id``. This service performs
        no authentication itself; retrieval is scoped to the given owner so a
        chunk owned by another user can never enter the prompt.

        Args:
            question: The user's question text.
            owner_id: The user id that owns the retrievable chunks. Empty for
                the backward-compatible ownerless path; the API layer always
                passes an authenticated user's id.

        Returns:
            The LLM response containing the answer and provenance metadata.

        Raises:
            LLMUnavailableError: If every configured provider fails.
        """
        contexts = self._retriever.retrieve(question, owner_id=owner_id)
        rag_prompt = self._prompt_builder.build_prompt(question, contexts)
        return await self._provider_manager.generate(rag_prompt.text)
