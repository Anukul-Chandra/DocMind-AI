from app.models.llm import LLMResponse
from app.services.chat.memory import ConversationMemory
from app.services.chat.models import ChatRequest, ChatResponse, SourceReference
from app.services.llm.provider_manager import ProviderManager
from app.services.llm.prompt_builder import PromptBuilder
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
    ) -> None:
        """Initialize the chat service with its collaborators.

        Args:
            retriever: Retrieves relevant document chunks for a question.
            prompt_builder: Builds the prompt to send to the LLM.
            provider_manager: Generates an answer via the configured LLM provider.
            memory: Preserves recent conversation history across follow-ups.
        """
        self._retriever = retriever
        self._prompt_builder = prompt_builder
        self._provider_manager = provider_manager
        self._memory = memory

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Answer a question using retrieved context and conversation history.

        Args:
            request: The chat request with the question and an optional
                ``conversation_id``.

        Returns:
            A chat response containing the answer, provenance, conversation id,
            and the source references used to generate the answer.
        """
        conversation_id = request.conversation_id or self._memory.create_conversation()
        history = self._memory.get_history(conversation_id)

        contexts = self._retriever.retrieve(request.question)
        rag_prompt = self._prompt_builder.build_prompt(
            request.question,
            contexts,
            history,
        )
        response: LLMResponse = await self._provider_manager.generate(rag_prompt.text)
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
                SourceReference(filename=source["filename"], chunk_id=source["chunk_id"])
                for source in rag_prompt.sources
            ],
            conversation_id=conversation_id,
        )