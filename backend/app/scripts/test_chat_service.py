"""Manual integration test for the end-to-end ChatService flow.

This script wires together the document retrieval, prompt building, and LLM
generation layers, inserts a small sample document into a FAISS-backed vector
store, and asks a single question through ChatService.

It is intended to be run manually only. It does not create any API endpoint or streaming behavior.
"""

import asyncio

from app.repositories.json.conversation_repository import JsonConversationRepository
from app.services.chat.memory import ConversationMemory
from app.services.chat.models import ChatRequest, ChatResponse
from app.services.chat.service import ChatService
from app.services.embedding import EmbeddingService
from app.services.llm.factory import build_provider_manager
from app.services.llm.provider_manager import LLMUnavailableError
from app.services.llm.prompt_builder import PromptBuilder
from app.services.vector_store import VectorStore
from app.services.vectorstore.metadata_store import MetadataStore
from app.services.vectorstore.retriever import SemanticRetriever

SAMPLE_FILENAME = "sample_docs.txt"
SAMPLE_CHUNKS: list[str] = [
    "Python is a high-level programming language.",
    "FastAPI is a modern Python web framework.",
    "FAISS is used for vector similarity search.",
]
QUESTION = "What is FastAPI?"


def build_retriever() -> SemanticRetriever:
    """Build a SemanticRetriever seeded with a small sample document.

Returns:
            A SemanticRetriever backed by an in-memory FAISS index that contains the
            sample chunks, ready for retrieval.
    """
    embedding_service = EmbeddingService()
    vector_store = VectorStore(dimension=embedding_service.get_embedding_dimension())
    metadata_store = MetadataStore()

    embeddings = embedding_service.generate_embeddings(SAMPLE_CHUNKS)
    vector_store.add_embeddings(embeddings)
    metadata_store.add_documents(SAMPLE_CHUNKS, SAMPLE_FILENAME)

    return SemanticRetriever(embedding_service, vector_store, metadata_store)


async def main() -> None:
    """Run the ChatService integration test end to end."""
    retriever = build_retriever()
    prompt_builder = PromptBuilder()
    provider_manager = build_provider_manager()
    chat_service = ChatService(
        retriever,
        prompt_builder,
        provider_manager,
        JsonConversationRepository(ConversationMemory()),
    )

    try:
        response: ChatResponse = await chat_service.chat(ChatRequest(question=QUESTION))
    except LLMUnavailableError as exc:
        print("=" * 60)
        print("All LLM providers failed.")
        for name, error in provider_manager.errors:
            print(f"  {name}: {error}")
        print(f"Reason: {exc}")
        print("=" * 60)
        return
    except Exception as exc:  # noqa: BLE001 - manual test should not crash
        print("=" * 60)
        print("Unexpected error during chat:")
        print(f"  {type(exc).__name__}: {exc}")
        print("=" * 60)
        return

    print("=" * 60)
    print("Question:")
    print(QUESTION)
    print()
    print("Answer:")
    print(response.answer)
    print()
    print("Provider:")
    print(response.provider)
    print()
    print("Model:")
    print(response.model)
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())