"""Manual integration test for the ChatService orchestration flow.

This script wires together the embedding, vector store, metadata store,
retrieval, prompt building, and LLM provider layers, indexes a few sample
chunks, and asks a single question through ChatService.

It prints the question, retrieved chunks, final prompt, provider, model, and
the answer. It is intended to be run manually only.
"""

import asyncio

from app.services.chat.chat_service import ChatService
from app.services.embedding import EmbeddingService
from app.services.llm.factory import build_provider_manager
from app.services.llm.prompt_builder import PromptBuilder
from app.services.llm.provider_manager import LLMUnavailableError, ProviderManager
from app.services.retrieval import Retriever
from app.services.vector_store import VectorStore
from app.services.vectorstore.metadata_store import MetadataStore
from app.services.vectorstore.retriever import SemanticRetriever

SAMPLE_FILENAME = "sample_docs.txt"
SAMPLE_CHUNKS: list[str] = [
    "FastAPI is a modern Python web framework.",
    "RAG stands for Retrieval-Augmented Generation.",
    "FAISS is a vector similarity search library.",
]
QUESTION = "What is RAG?"


def build_retriever() -> SemanticRetriever:
    """Build a SemanticRetriever seeded with a small sample document.

    Returns:
        A SemanticRetriever backed by an in-memory FAISS index that contains
        the sample chunks, ready for retrieval.
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
    retriever: Retriever = build_retriever()
    prompt_builder = PromptBuilder()
    provider_manager: ProviderManager = build_provider_manager()
    chat_service = ChatService(retriever, prompt_builder, provider_manager)

    contexts = retriever.retrieve(QUESTION)
    rag_prompt = prompt_builder.build_prompt(QUESTION, contexts)

    print("=" * 60)
    print("Question:")
    print(QUESTION)
    print()
    print("Retrieved Chunks:")
    for index, chunk in enumerate(contexts, start=1):
        print(f"  {index}. {chunk['text']}")
    print()
    print("Final Prompt:")
    print(rag_prompt.text)
    print("=" * 60)

    try:
        response = await chat_service.chat(QUESTION)
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

    print()
    print("Provider:")
    print(response.provider)
    print()
    print("Model:")
    print(response.model)
    print()
    print("Answer:")
    print(response.text)
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
