from app.models.llm import LLMResponse
from app.repositories.interfaces import ConversationRepository, DocumentRepository
from app.services.chat.query_router import QueryCategory, QueryRouter
from app.services.llm.prompt_builder import PromptBuilder
from app.services.llm.provider_manager import ProviderManager
from app.services.rag.crag import CragOrchestrator
from app.services.rag.query_rewriter import QueryRewriter
from app.services.rag.retrieval_evaluator import RetrievalEvaluator
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
        retrieval_evaluator: RetrievalEvaluator | None = None,
        query_rewriter: QueryRewriter | None = None,
        conversation_repository: ConversationRepository | None = None,
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
            retrieval_evaluator: Evaluates retrieval quality for
                document-grounded queries, or None to skip evaluation.
            query_rewriter: Rewrites weak queries into better retrieval queries
                for corrective retrieval.  When both ``retrieval_evaluator``
                and ``query_rewriter`` are present, DOCUMENT queries run through
                a single corrective-retrieval pass.  If either is None, the
                service degrades to plain retrieval.
            conversation_repository: Persists the question/answer exchange to
                the owning user's conversation history, or None to skip
                history recording.
        """
        self._retriever = retriever
        self._prompt_builder = prompt_builder
        self._provider_manager = provider_manager
        self._document_repository = document_repository
        self._query_router = query_router or QueryRouter()
        self._retrieval_evaluator = retrieval_evaluator
        self._conversation_repository = conversation_repository

        self._crag: CragOrchestrator | None = None
        if retrieval_evaluator is not None and query_rewriter is not None:
            self._crag = CragOrchestrator(
                retriever=retriever,
                evaluator=retrieval_evaluator,
                rewriter=query_rewriter,
            )

    async def chat(
        self,
        question: str,
        owner_id: str = "",
        images: list[dict] | None = None,
        conversation_id: str | None = None,
    ) -> LLMResponse:
        """Answer a question, routing it to the appropriate path.

        The caller (the API layer) is responsible for authentication and for
        passing the authenticated user's ``owner_id``. Retrieval and document
        listing are scoped to the given owner so another user's chunks or
        documents can never be used. When ``conversation_id`` is provided and
        a conversation repository is configured, the exchange is recorded to
        the conversation history.

        Args:
            question: The user's question text.
            owner_id: The user id that owns the retrievable chunks and
                documents. Empty for the backward-compatible ownerless path;
                the API layer always passes an authenticated user's id.
            images: Optional list of base64-encoded image dicts with keys
                ``mime`` and ``data``. Passed through to the provider for
                multimodal requests.
            conversation_id: The conversation to record the exchange in, or
                None to skip history recording.

        Returns:
            The LLM response containing the answer and provenance metadata.

        Raises:
            LLMUnavailableError: If every provider fails.
        """
        route = self._query_router.classify_with_embedding(
            question, owner_id=owner_id
        )
        category = route.category
        query_embedding = route.query_embedding
        if category is QueryCategory.METADATA:
            response = self._answer_metadata(owner_id)
        elif category is QueryCategory.GENERAL:
            prompt = self._prompt_builder.build_general_prompt(question)
            response = await self._provider_manager.generate(
                prompt.text, images=images,
            )
        else:
            if self._crag is not None:
                contexts = await self._crag.retrieve(
                    question,
                    owner_id=owner_id,
                    query_embedding=query_embedding,
                )
            else:
                contexts = self._retriever.retrieve(
                    question,
                    owner_id=owner_id,
                    query_embedding=query_embedding,
                )
                if self._retrieval_evaluator is not None:
                    self._retrieval_evaluator.evaluate(question, contexts)
            rag_prompt = self._prompt_builder.build_prompt(question, contexts)
            response = await self._provider_manager.generate(
                rag_prompt.text, images=images,
            )
            response.category = category.value
            response.sources = contexts
        self._record_exchange(
            conversation_id, owner_id, question, response
        )
        return response

    def _record_exchange(
        self,
        conversation_id: str | None,
        owner_id: str,
        question: str,
        response: object,
    ) -> None:
        """Persist a chat exchange to the conversation history when available.

        Recording is best-effort: a missing conversation repository, an empty
        owner, or an ownership mismatch must never fail the chat turn, so
        persistence errors are swallowed. The answer text is read defensively
        so responses that are plain strings (as in some tests) do not crash.

        Args:
            conversation_id: The conversation to record into, or None.
            owner_id: The user id that owns the conversation.
            question: The user's question.
            response: The assistant's response object (an ``LLMResponse`` or a
                plain string answer).
        """
        if (
            conversation_id is None
            or not owner_id
            or self._conversation_repository is None
        ):
            return
        answer = getattr(response, "text", None)
        if answer is None:
            answer = response if isinstance(response, str) else ""
        try:
            self._conversation_repository.add_exchange(
                conversation_id,
                owner_id,
                question,
                str(answer),
            )
        except Exception:
            return

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
                category="metadata",
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
                category="metadata",
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
            category="metadata",
        )
