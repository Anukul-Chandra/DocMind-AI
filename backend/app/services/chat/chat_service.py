from app.models.llm import LLMResponse
from app.repositories.interfaces import DocumentRepository
from app.services.chat.query_router import QueryCategory, QueryRouter
from app.services.llm.prompt_builder import PromptBuilder
from app.services.llm.provider_manager import ProviderManager
from app.services.retrieval.base import Retriever


class ChatService:
    """Orchestrate query routing, retrieval, prompt construction, and generation.

    This service is the composition root for a single chat turn. It classifies
    each question into a routing category:

    - GENERAL: sends a plain prompt to the LLM gateway, no document retrieval.
    - DOCUMENT: retrieves the most relevant chunks and builds a grounded
      prompt from them.
    - METADATA: answers from the document list without retrieval or an LLM.

    It depends only on the ``Retriever``, ``PromptBuilder``,
    ``ProviderManager``, ``DocumentRepository``, and ``QueryRouter``
    abstractions it receives, and knows nothing about concrete providers such
    as OpenRouter, Gemini, or Groq.
    """

    def __init__(
        self,
        retriever: Retriever,
        prompt_builder: PromptBuilder,
        provider_manager: ProviderManager,
        document_repository: DocumentRepository | None = None,
        query_router: QueryRouter | None = None,
    ) -> None:
        """Initialize the chat service with its collaborators.

        Args:
            retriever: Retrieves the most relevant document chunks for a
                document-grounded question.
            prompt_builder: Builds the final prompt from the question and the
                retrieved chunks (or a plain prompt for general questions).
            provider_manager: Generates the answer via the configured LLM
                provider.
            document_repository: Provides the user's document list for
                metadata questions, or None if the path is unavailable.
            query_router: Classifies questions into routing categories, or
                None to use the default deterministic router.
        """
        self._retriever = retriever
        self._prompt_builder = prompt_builder
        self._provider_manager = provider_manager
        self._document_repository = document_repository
        self._query_router = query_router or QueryRouter()

    async def chat(self, question: str, owner_id: str = "") -> LLMResponse:
        """Answer a question, routing it to the appropriate path.

        The caller (the API layer) is responsible for authentication and for
        passing the authenticated user's ``owner_id``. Retrieval and document
        listing are scoped to the given owner so another user's chunks or
        documents can never be used.

        Args:
            question: The user's question text.
            owner_id: The user id that owns the retrievable chunks and
                documents. Empty for the backward-compatible ownerless path;
                the API layer always passes an authenticated user's id.

        Returns:
            The LLM response containing the answer and provenance metadata.

        Raises:
            LLMUnavailableError: If every provider fails.
        """
        category = self._query_router.classify(question)
        if category is QueryCategory.METADATA:
            return self._answer_metadata(owner_id)
        if category is QueryCategory.GENERAL:
            prompt = self._prompt_builder.build_general_prompt(question)
            return await self._provider_manager.generate(prompt.text)
        contexts = self._retriever.retrieve(question, owner_id=owner_id)
        rag_prompt = self._prompt_builder.build_prompt(question, contexts)
        return await self._provider_manager.generate(rag_prompt.text)

    def _answer_metadata(self, owner_id: str) -> LLMResponse:
        """Answer a document-list question without retrieval or an LLM call.

        Args:
            owner_id: The user id whose documents to list.

        Returns:
            An LLMResponse summarizing the user's uploaded documents.
        """
        if self._document_repository is None:
            return LLMResponse(
                text="Your document list is not available right now.",
                provider="metadata",
                model="",
            )
        documents = [
            document
            for document in self._document_repository.list_documents(owner_id)
            if not document.deleted
        ]
        if not documents:
            return LLMResponse(
                text="You have no uploaded documents yet.",
                provider="metadata",
                model="",
            )
        filenames: list[str] = []
        for document in documents:
            if document.filename not in filenames:
                filenames.append(document.filename)
        names = ", ".join(filenames)
        noun = "document" if len(filenames) == 1 else "documents"
        return LLMResponse(
            text=f"You have {len(filenames)} uploaded {noun}: {names}.",
            provider="metadata",
            model="",
        )
