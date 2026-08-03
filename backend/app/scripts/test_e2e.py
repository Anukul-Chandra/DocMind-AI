"""
End-to-end verification for the DocMind AI release candidate (RC-1).

Builds the full application pipeline using only existing services against an
isolated temporary directory, then verifies every stage:

    upload -> chunking -> embedding -> FAISS -> metadata persistence ->
    retrieval -> hybrid search -> reranking -> chat -> memory -> sources ->
    request logging -> provider/model provenance.

Usage (from backend/):
    PYTHONPATH=. ../.venv/bin/python app/scripts/test_e2e.py

Exit status is non-zero if any stage fails.
"""

import asyncio
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import fitz

from app.core.config import settings
from app.repositories.json.conversation_repository import JsonConversationRepository
from app.repositories.json.log_repository import JsonLogRepository
from app.services.chat.memory import ConversationMemory
from app.services.chat.models import ChatRequest
from app.services.chat.service import ChatService
from app.services.document_registry import DocumentRegistry
from app.services.embedding import EmbeddingService
from app.services.indexing import DocumentIndexService
from app.services.llm.factory import build_provider_manager
from app.services.llm.prompt_builder import PromptBuilder
from app.services.logging.request_logger import RequestLogger
from app.services.retrieval import BM25Retriever, HybridRetriever
from app.services.retrieval.reranker import SemanticReranker, TOKEN_PATTERN
from app.services.vector_store import VectorStore
from app.services.vectorstore.metadata_store import MetadataStore
from app.services.vectorstore.retriever import SemanticRetriever
from app.services.vectorstore.workspace import DEFAULT_WORKSPACE

SAMPLE_TEXT = (
    "DocMind AI is an intelligent document analysis system. It extracts text "
    "from PDF documents, cleans and chunks the content, generates embeddings, "
    "and stores them in a FAISS vector index. Retrieval combines BM25 keyword "
    "search with semantic similarity and reranks the fused results before "
    "sending the retrieved context to an LLM provider for an answer."
)
QUESTION = "How does DocMind AI retrieve document chunks?"


def create_sample_pdf(path: Path) -> None:
    """Create a small PDF containing the sample document text.

    Args:
        path: The file path of the PDF to create.
    """
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), SAMPLE_TEXT)
    document.save(str(path))
    document.close()


def run_checks(results: list[tuple[str, bool, str]], steps: list[tuple[str, bool, str]]) -> None:
    """Extend the results list with the outcomes of the given steps.

    Args:
        results: The list accumulating (name, passed, detail) tuples.
        steps: The steps to append, each a (name, passed, detail) tuple.
    """
    results.extend(steps)


def print_report(results: list[tuple[str, bool, str]]) -> None:
    """Print the RC-1 verification report.

    Args:
        results: The list of (name, passed, detail) tuples to report.
    """
    print("=" * 40)
    print("DocMind AI RC-1 Verification")
    print("=" * 40)
    print()
    for name, passed, _detail in results:
        status = "PASS" if passed else "FAIL"
        print(f"{name:<20}{status}")
    print()
    print("=" * 40)
    print()
    print("OVERALL")
    print()
    overall = all(passed for _, passed, _ in results)
    print("PASS" if overall else "FAIL")
    print()
    print("=" * 40)
    print()

    failures = [(name, detail) for name, passed, detail in results if not passed]
    if failures:
        print("Failures:")
        for name, detail in failures:
            print(f"  {name}: {detail}")
        print()


async def main() -> int:
    """Run every verification stage and return the process exit code.

    Returns:
        0 when all stages pass, otherwise 1.
    """
    results: list[tuple[str, bool, str]] = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        pdf_path = tmp / "sample.pdf"
        faiss_path = tmp / "faiss" / "index.faiss"
        metadata_path = tmp / "metadata.json"
        documents_path = tmp / "documents.json"
        log_dir = tmp / "logs"

        original_faiss = settings.faiss_index_path
        original_metadata = settings.metadata_path
        settings.faiss_index_path = str(faiss_path)
        settings.metadata_path = str(metadata_path)
        try:
            embedding_service = EmbeddingService()
            vector_store = VectorStore(
                dimension=embedding_service.get_embedding_dimension()
            )
            metadata_store = MetadataStore()
            document_registry = DocumentRegistry(documents_path)
            index_service = DocumentIndexService(
                embedding_service,
                vector_store,
                metadata_store,
            )

            uploaded = False
            chunks_indexed = 0
            embeddings_generated = 0
            try:
                create_sample_pdf(pdf_path)
                result = index_service.index_document(
                    str(pdf_path),
                    workspace_id=DEFAULT_WORKSPACE,
                    document_id="e2e-doc",
                )
                uploaded = True
                chunks_indexed = result.total_chunks
                embeddings_generated = result.total_embeddings
                detail = f"indexed {result.filename}"
            except Exception as exc:  # noqa: BLE001 - verification must not crash
                detail = str(exc)
            run_checks(
                results,
                [
                    ("Upload", uploaded, detail),
                    (
                        "Chunking",
                        uploaded and chunks_indexed > 0,
                        f"{chunks_indexed} chunks",
                    ),
                    (
                        "Embedding",
                        uploaded
                        and embeddings_generated > 0
                        and embeddings_generated == chunks_indexed,
                        f"{embeddings_generated} embeddings",
                    ),
                ],
            )

            faiss_ok = False
            try:
                reloaded = VectorStore.load(
                    str(faiss_path),
                    dimension=embedding_service.get_embedding_dimension(),
                )
                faiss_ok = reloaded._index.ntotal == chunks_indexed
                detail = f"{reloaded._index.ntotal} vectors on disk"
            except Exception as exc:  # noqa: BLE001 - verification must not crash
                detail = str(exc)
            run_checks(results, [("FAISS", faiss_ok, detail)])

            metadata_ok = False
            try:
                reloaded_metadata = MetadataStore()
                reloaded_metadata.load(str(metadata_path))
                metadata_ok = (
                    len(reloaded_metadata.get_all_documents()) == chunks_indexed
                )
                detail = (
                    f"{len(reloaded_metadata.get_all_documents())} records on disk"
                )
            except Exception as exc:  # noqa: BLE001 - verification must not crash
                detail = str(exc)
            run_checks(results, [("Metadata", metadata_ok, detail)])

            semantic_retriever = SemanticRetriever(
                embedding_service,
                vector_store,
                metadata_store,
                document_registry,
            )
            bm25_retriever = BM25Retriever(
                metadata_store,
                document_registry,
            )
            hybrid_retriever = HybridRetriever(
                semantic_retriever=semantic_retriever,
                bm25_retriever=bm25_retriever,
            )
            reranker = SemanticReranker()

            retrieval_ok = False
            try:
                retrieval_results = semantic_retriever.retrieve(
                    QUESTION, k=3, workspace_id=DEFAULT_WORKSPACE
                )
                retrieval_ok = bool(retrieval_results)
                detail = f"{len(retrieval_results)} chunks"
            except Exception as exc:  # noqa: BLE001 - verification must not crash
                detail = str(exc)
            run_checks(results, [("Retrieval", retrieval_ok, detail)])

            hybrid_ok = False
            try:
                hybrid_results = hybrid_retriever.retrieve(
                    QUESTION, k=3, workspace_id=DEFAULT_WORKSPACE
                )
                hybrid_ok = bool(hybrid_results)
                detail = f"{len(hybrid_results)} chunks"
            except Exception as exc:  # noqa: BLE001 - verification must not crash
                detail = str(exc)
            run_checks(results, [("Hybrid Search", hybrid_ok, detail)])

            rerank_ok = False
            try:
                candidates = semantic_retriever.retrieve(
                    QUESTION, k=5, workspace_id=DEFAULT_WORKSPACE
                )
                reranked = reranker.rerank(QUESTION, candidates, k=len(candidates))
                query_tokens = Counter(TOKEN_PATTERN.findall(QUESTION.lower()))
                scores = [
                    reranker._score(query_tokens, candidate.get("text", ""))
                    for candidate in reranked
                ]
                rerank_ok = (
                    bool(reranked)
                    and len(reranked) == len(candidates)
                    and all(
                        scores[i] >= scores[i + 1]
                        for i in range(len(scores) - 1)
                    )
                )
                detail = (
                    f"{len(reranked)} chunks, best score {scores[0]:.4f}"
                    if reranked
                    else "no chunks"
                )
            except Exception as exc:  # noqa: BLE001 - verification must not crash
                detail = str(exc)
            run_checks(results, [("Reranking", rerank_ok, detail)])

            chat_ok = False
            memory_ok = False
            sources_ok = False
            provider_ok = False
            chat_detail = "chat not attempted"
            memory_detail = "no history"
            sources_detail = "no sources"
            provider_detail = "no provider reported"
            try:
                memory = JsonConversationRepository(ConversationMemory())
                request_logger = JsonLogRepository(RequestLogger(log_dir))
                chat_service = ChatService(
                    hybrid_retriever,
                    PromptBuilder(),
                    build_provider_manager(),
                    memory,
                    request_logger,
                )
                response = await chat_service.chat(
                    ChatRequest(question=QUESTION)
                )
                chat_ok = bool(response.answer)
                chat_detail = f"answer {len(response.answer)} chars"

                history = memory.get_history(response.conversation_id)
                memory_ok = len(history) >= 2
                memory_detail = f"{len(history)} messages"

                sources_ok = bool(response.sources)
                sources_detail = f"{len(response.sources)} sources"

                provider_ok = bool(response.provider) and bool(response.model)
                provider_detail = f"provider={response.provider}, model={response.model}"
            except Exception as exc:  # noqa: BLE001 - verification must not crash
                chat_detail = str(exc)

            today = datetime.now(timezone.utc).date().isoformat()
            log_file = log_dir / f"{today}.jsonl"
            logging_ok = log_file.exists() and log_file.stat().st_size > 0
            logging_detail = str(log_file) if logging_ok else "no log file"

            run_checks(
                results,
                [
                    ("Chat", chat_ok, chat_detail),
                    ("Memory", memory_ok, memory_detail),
                    ("Sources", sources_ok, sources_detail),
                    ("Logging", logging_ok, logging_detail),
                    ("Provider", provider_ok, provider_detail),
                ],
            )
        finally:
            settings.faiss_index_path = original_faiss
            settings.metadata_path = original_metadata

    print_report(results)
    return 0 if all(passed for _, passed, _ in results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
