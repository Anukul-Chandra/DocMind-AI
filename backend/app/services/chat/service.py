import time
import uuid
from datetime import datetime, timezone

from app.models.llm import LLMResponse
from app.services.chat.memory import ConversationMemory
from app.services.chat.models import ChatRequest, ChatResponse, SourceReference
from app.services.llm.provider_manager import ProviderManager
from app.services.llm.prompt_builder import PromptBuilder
from app.services.logging.request_logger import RequestLogEntry, RequestLogger
from app.services.vectorstore.retriever import Retriever


class ChatService:
    """Orchestrate document retrieval, prompt building, and LLM generation.

    This service is the composition root for a single chat turn, with recent
    conversation history preserved in memory. It depends only on the
    abstractions it receives (retriever, prompt builder, provider manager, and
    conversation memory) and knows nothing about concrete LLM providers such as
    OpenRouter, Gemini, or Groq.
    """

    def __init__(
        self,
        retriever: Retriever,
        prompt_builder: PromptBuilder,
        provider_manager: ProviderManager,
        memory: ConversationMemory,
        request_logger: RequestLogger | None = None,
    ) -> None:
        """Initialize the chat service with its collaborators.

        Args:
            retriever: Retrieves relevant document chunks for a question.
            prompt_builder: Builds the prompt to send to the LLM.
            provider_manager: Generates an answer via the configured LLM provider.
            memory: Preserves recent conversation history across follow-ups.
            request_logger: Optional best-effort logger for chat requests.
        """
        self._retriever = retriever
        self._prompt_builder = prompt_builder
        self._provider_manager = provider_manager
        self._memory = memory
        self._request_logger = request_logger

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Ask the question using retrieved context and conversation history.

        Args:
            request: The chat request with the question, an optional
                ``conversation_id``, and a ``workspace_id``.

        Returns:
            A chat response containing the answer, provenance, conversation id,
            and the source references used to generate the answer.
        """
        request_id = str(uuid.uuid4())
        start = time.perf_counter()
        conversation_id = request.conversation_id or self._memory.create_conversation()
        provider = ""
        model = ""
        chunk_count = 0
        success = True
        error_message = None

        try:
            contexts = self._retriever.retrieve(
                request.question,
                workspace_id=request.workspace_id,
            )
            chunk_count = len(contexts)
            rag_prompt = self._prompt_builder.build_prompt(
                request.question,
                contexts,
                self._memory.get_history(conversation_id),
            )
            response: LLMResponse = await self._provider_manager.generate(rag_prompt.text)
            provider = response.provider
            model = response.model
            self._memory.add_exchange(
                conversation_id,
                request.question,
                response.text,
            )
            return ChatResponse(
                answer=response.text,
                provider=response.provider,
                model=response.model,
                sources=[
                    SourceReference(
                        filename=source["filename"], chunk_id=source["chunk_id"]
                    )
                    for source in rag_prompt.sources
                ],
                conversation_id=conversation_id,
            )
        except Exception as exc:
            success = False
            error_message = str(exc)
            raise
        finally:
            response_time_ms = (time.perf_counter() - start) * 1000.0
            self._write_log(
                request,
                request_id,
                conversation_id,
                provider,
                model,
                chunk_count,
                response_time_ms,
                success,
                error_message,
            )

    def _write_log(
        self,
        request: ChatRequest,
        request_id: str,
        conversation_id: str,
        provider: str,
        model: str,
        chunk_count: int,
        response_time_ms: float,
        success: bool,
        error_message: str | None,
    ) -> None:
        """Write a best-effort log entry for a completed chat request.

        Args:
            request: The original chat request.
            request_id: The generated request identifier.
            conversation_id: The conversation identifier.
            provider: The provider used, or an empty string.
            model: The model used, or an empty string.
            chunk_count: The retrieved chunk count.
            response_time_ms: The response time in milliseconds.
            success: Whether the request succeeded.
            error_message: An optional error message on failure.
        """
        if self._request_logger is None:
            return
        timestamp = datetime.now(timezone.utc).isoformat()
        self._request_logger.log(
            RequestLogEntry(
                request_id=request_id,
                timestamp=timestamp,
                workspace_id=request.workspace_id,
                conversation_id=conversation_id,
                provider=provider,
                model=model,
                question=request.question,
                retrieved_chunk_count=chunk_count,
                response_time_ms=response_time_ms,
                success=success,
                error_message=error_message,
            )
        )