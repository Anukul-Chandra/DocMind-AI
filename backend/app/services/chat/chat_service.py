from app.models.llm import LLMResponse
from app.repositories.interfaces import (
    ConversationRepository,
    DocumentRepository,
    UserMemoryRepository,
)
from app.services.chat.conversations_service import ConversationNotFoundError
from app.services.chat.query_router import QueryCategory, QueryRouter
from app.services.llm.prompt_builder import PromptBuilder
from app.services.llm.provider_manager import ProviderManager
from app.services.rag.crag import CragOrchestrator
from app.services.rag.query_rewriter import QueryRewriter
from app.services.rag.retrieval_evaluator import RetrievalEvaluator
from app.services.retrieval.base import Retriever
from app.services.chat.user_memory import UserMemoryExtractor
import logging
import time

logger = logging.getLogger(__name__)


# Keep the prompt history bounded to the same ten exchange window used by the
# JSON conversation store.  A complete exchange is two messages.
HISTORY_MESSAGE_LIMIT = 20


def _image_data_urls(images: list[dict] | None) -> list[str]:
    """Convert provider image payloads into browser-renderable data URLs."""
    if not images:
        return []
    return [
        f"data:{image.get('mime', 'image/png')};base64,{image['data']}"
        for image in images
        if image.get("data")
    ]


def _images_from_data_urls(stored: list[str] | None) -> tuple[list[dict], list[str]]:
    """Split persisted image data URLs back into provider payloads.

    Args:
        stored: The ``images`` list persisted on a user message
            (``data:<mime>;base64,<data>`` URLs).

    Returns:
        A ``(provider_images, storage_images)`` pair: provider payloads with
        ``mime``/``data`` keys for the LLM call, and the original storage
        URLs (only the well-formed ones) to re-record with the new exchange.
        Malformed entries are dropped from both lists.
    """
    provider_images: list[dict] = []
    storage_images: list[str] = []
    for url in stored or []:
        if not isinstance(url, str) or not url.startswith("data:") or "," not in url:
            continue
        header, data = url.split(",", 1)
        if ";base64" not in header or not data:
            continue
        mime = header[len("data:"):].split(";")[0].strip() or "image/png"
        provider_images.append({"mime": mime, "data": data})
        storage_images.append(url)
    return provider_images, storage_images


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
        user_memory_repository: UserMemoryRepository | None = None,
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
            user_memory_repository: Repository for user memory.
        """
        self._retriever = retriever
        self._prompt_builder = prompt_builder
        self._provider_manager = provider_manager
        self._document_repository = document_repository
        self._query_router = query_router or QueryRouter()
        self._retrieval_evaluator = retrieval_evaluator
        self._conversation_repository = conversation_repository
        self._user_memory_repository = user_memory_repository
        self._user_memory_extractor = UserMemoryExtractor()

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
        _t_start = time.perf_counter()
        _t_retrieve = 0.0

        _t0 = time.perf_counter()
        history = self._load_history(conversation_id, owner_id)
        _t_history = time.perf_counter() - _t0

        _t0 = time.perf_counter()
        self._save_user_memory(question, owner_id)
        user_memory = self._load_user_memory(owner_id)
        _t_memory = time.perf_counter() - _t0

        _t0 = time.perf_counter()
        response = await self._generate_answer(
            question, history, user_memory, images, owner_id=owner_id
        )
        _t_generate = time.perf_counter() - _t0

        _t0 = time.perf_counter()
        self._record_exchange(
            conversation_id, owner_id, question, response, images
        )
        _t_persist = time.perf_counter() - _t0

        _t_total = time.perf_counter() - _t_start
        logger.info(
            "chat_timing total=%.3fs history=%.4fs memory=%.4fs "
            "generate=%.3fs persist=%.4fs "
            "category=%s provider=%s model=%s",
            _t_total, _t_history, _t_memory,
            _t_generate, _t_persist, getattr(response, "category", ""),
            getattr(response, "provider", ""),
            getattr(response, "model", ""),
        )

        return response

    async def regenerate_branch(
        self,
        conversation_id: str,
        owner_id: str,
        message_index: int,
        new_question: str | None = None,
    ) -> LLMResponse:
        """Regenerate the assistant response for one user message as a branch.

        The superseded branch is replaced atomically from the caller's point
        of view: the answer is generated against the truncated history
        (everything before ``message_index``) and only persisted on success,
        so a failed regeneration never corrupts the stored conversation and
        the old branch can never leak into the new prompt.

        For ``User A / Assistant A / User B / Assistant B`` with
        ``message_index`` pointing at ``User B``, the prompt sees only
        ``User A / Assistant A`` plus the (possibly edited) ``User B`` text,
        and the stored history becomes
        ``User A / Assistant A / User B(-edited) / Assistant B-new``.

        Args:
            conversation_id: The conversation to rewrite.
            owner_id: The user id that owns the conversation.
            message_index: Position of the target user message in the stored
                message list (0-based, counting both roles).
            new_question: Edited replacement text, or None to reuse the
                stored message (pure regenerate).

        Returns:
            The new LLM response.

        Raises:
            ConversationNotFoundError: If the conversation is unknown or
                belongs to another owner.
            ValueError: If the index is out of range, does not point at a
                user message, or the resulting question is empty.
            LLMUnavailableError: If every provider fails (nothing persisted).
        """
        if self._conversation_repository is None:
            raise ValueError("Conversation history is unavailable.")
        if not conversation_id or not owner_id:
            raise ValueError("conversation_id and owner_id are required.")
        if self._conversation_repository.get_conversation(
            conversation_id, owner_id
        ) is None:
            raise ConversationNotFoundError(conversation_id)

        stored = self._conversation_repository.get_messages(
            conversation_id, owner_id
        )
        if message_index < 0 or message_index >= len(stored):
            raise ValueError("message_index is out of range.")
        target = stored[message_index]
        if target.role != "user":
            raise ValueError("message_index must point at a user message.")

        if new_question is not None:
            question = new_question.strip()
            if not question:
                raise ValueError("Edited message must not be empty.")
        else:
            question = target.content.strip()
            if not question:
                raise ValueError("Cannot regenerate an empty message.")

        # Attachments reuse: the backend persists image data URLs on the user
        # message, so the original multimodal request can be reconstructed
        # without re-uploading files.
        provider_images, storage_images = _images_from_data_urls(
            target.images
        )

        # Truncated context: only the exchanges preceding the target message.
        keep = message_index
        history = [
            {"role": message.role, "content": message.content}
            for message in stored[:keep][-HISTORY_MESSAGE_LIMIT:]
        ]

        _t_start = time.perf_counter()
        self._save_user_memory(question, owner_id)
        user_memory = self._load_user_memory(owner_id)
        response = await self._generate_answer(
            question, history, user_memory,
            provider_images if provider_images else None,
            owner_id=owner_id,
        )

        # Replace the branch only after a successful generation.
        if not self._conversation_repository.truncate_messages(
            conversation_id, owner_id, keep
        ):
            raise ConversationNotFoundError(conversation_id)
        answer = getattr(response, "text", None)
        if answer is None:
            answer = response if isinstance(response, str) else ""
        self._conversation_repository.add_exchange(
            conversation_id, owner_id, question, str(answer), storage_images
        )
        logger.info(
            "chat_regenerate total=%.3fs category=%s provider=%s model=%s "
            "conversation=%s index=%d edited=%s",
            time.perf_counter() - _t_start,
            getattr(response, "category", ""),
            getattr(response, "provider", ""),
            getattr(response, "model", ""),
            conversation_id, message_index, new_question is not None,
        )
        return response

    async def _generate_answer(
        self,
        question: str,
        history: list[dict[str, str]],
        user_memory: list[dict[str, str]],
        images: list[dict] | None,
        owner_id: str = "",
    ) -> LLMResponse:
        """Route one question and generate its answer against ``history``.

        Shared by :meth:`chat` (full stored history) and
        :meth:`regenerate_branch` (truncated branch history) so both paths
        use identical routing, retrieval, and prompt construction.

        Args:
            question: The user's question text.
            history: Prior ``{"role", "content"}`` turns visible to the LLM.
            user_memory: The owner's durable memories.
            images: Optional base64 image payloads for multimodal providers.
            owner_id: The user id scoping retrieval and document listing.

        Returns:
            The LLM response with routing provenance filled in.
        """
        route = self._query_router.classify_with_embedding(
            question, owner_id=owner_id
        )

        category = route.category
        query_embedding = route.query_embedding

        if category is QueryCategory.METADATA:
            return self._answer_metadata(owner_id)
        if category is QueryCategory.GENERAL:
            prompt = self._prompt_builder.build_general_prompt(
                question, history=history, user_memory=user_memory
            )
            return await self._provider_manager.generate(
                prompt.text, images=images,
            )

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

        if self._crag is None and self._retrieval_evaluator is not None:
            self._retrieval_evaluator.evaluate(question, contexts)

        rag_prompt = self._prompt_builder.build_prompt(
            question, contexts, history=history, user_memory=user_memory
        )
        response = await self._provider_manager.generate(
            rag_prompt.text, images=images,
        )
        response.category = category.value
        response.sources = contexts
        return response

    def _load_user_memory(self, owner_id: str) -> list[dict[str, str]]:
        """Load only durable memories belonging to the authenticated user."""
        if not owner_id or self._user_memory_repository is None:
            return []
        try:
            return [
                {"key": memory.key, "value": memory.value}
                for memory in self._user_memory_repository.list_memories(owner_id)
            ]
        except Exception as exc:
            logger.warning("Failed to load user memory for owner %s: %s", owner_id, exc)
            return []

    def _save_user_memory(self, question: str, owner_id: str) -> None:
        """Persist an explicit durable fact without saving ordinary messages."""
        if not owner_id or self._user_memory_repository is None:
            return
        candidate = self._user_memory_extractor.extract(question)
        if candidate is None:
            return
        try:
            self._user_memory_repository.upsert_memory(
                owner_id, candidate.key, candidate.value
            )
        except Exception as exc:
            logger.warning("Failed to save user memory for owner %s: %s", owner_id, exc)

    def _load_history(
        self, conversation_id: str | None, owner_id: str
    ) -> list[dict[str, str]]:
        """Load the bounded, owner-scoped history preceding this chat turn.

        The API route validates ownership before calling this service.  The
        repository applies the same owner scope as defense in depth, so a
        conversation ID can never expose messages from another user.
        """
        if (
            conversation_id is None
            or not owner_id
            or self._conversation_repository is None
        ):
            return []
        messages = self._conversation_repository.get_messages(
            conversation_id, owner_id
        )
        return [
            {"role": message.role, "content": message.content}
            for message in messages[-HISTORY_MESSAGE_LIMIT:]
        ]

    def _record_exchange(
        self,
        conversation_id: str | None,
        owner_id: str,
        question: str,
        response: object,
        images: list[dict] | None = None,
    ) -> None:
        """Persist a chat exchange to the conversation history when available.

        Recording is best-effort: a missing conversation repository, an empty
        owner, or an ownership mismatch must never fail the chat turn.
        Persistence errors are logged at warning level so they are visible
        in production monitoring but do not fail the request. The answer
        text is read defensively so responses that are plain strings (as in
        some tests) do not crash.

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
                _image_data_urls(images),
            )
        except Exception as exc:
            logger.warning(
                "Failed to record exchange for conversation %s owner %s: %s",
                conversation_id,
                owner_id,
                exc,
            )

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
