"""API integration tests for owner-scoped retrieval and chat.

Exercises the real FastAPI endpoints (``/retrieve``, ``/chat``,
``/documents/upload``) against an isolated, deterministic retrieval stack:

* User A uploads and indexes a document about DocMind.
* User B uploads and indexes a document about currency exchange.
* The full embedding/FAISS/BM25/hybrid/reranker pipeline runs with a
  deterministic dependency-free fake embedding service, and chat uses the real
  ChatService orchestration with a recording fake LLM provider.

Verified scenarios:
    A. Upload document A (User A) and document B (User B).
    B. User A calls /retrieve with a query matching B's document. Expected:
       B's chunk is NOT returned.
    C. User B calls /retrieve with a query matching B's document. Expected:
       B's chunk IS returned.
    D. User A calls /chat with a query matching B's document. Expected: the
       RAG prompt context contains only A-owned chunks (B's text absent).
    E. User B calls /chat with a query matching B's document. Expected:
       B-owned chunks are usable (B's text present in the prompt context).
    F. Missing / invalid authentication on /retrieve and /chat returns 401.

The retrieval-layer isolation itself is covered in
``test_retrieval_ownership.py``; this script verifies the wiring from the
authenticated user to retrieval through the real routes.

Usage (from backend/):
    python -m app.scripts.test_retrieval_ownership_api

Exit status is non-zero if any check fails.
"""

import sys
import tempfile
from pathlib import Path

import fitz
from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_auth_service,
    get_chat_service,
    get_document_registry,
    get_document_repository,
    get_document_service,
    get_embedding_service,
    get_metadata_store,
    get_retriever,
    get_vector_store,
)
from app.main import app
from app.repositories.json.document_repository import JsonDocumentRepository
from app.repositories.json.user_repository import JsonUserRepository
from app.services.auth import AuthService, JWTService, PasswordService
from app.services.chat.chat_service import ChatService
from app.services.document import Chunker, DocumentService, PDFProcessor
from app.services.document_registry import DocumentRegistry
from app.services.llm.providers.base import BaseProvider
from app.services.llm.prompt_builder import PromptBuilder
from app.services.retrieval import BM25Retriever, HybridRetriever
from app.services.vector_store import VectorStore
from app.services.vectorstore.metadata_store import MetadataStore
from app.services.vectorstore.retriever import SemanticRetriever
from app.services.vectorstore.workspace import DEFAULT_WORKSPACE

PASSWORD = "super-secret-1"
TOKEN_SECRET = "test-token-secret"

A_TEXT = (
    "DocMind performs semantic retrieval over indexed PDFs with owner scoping "
    "so each user only ever sees their own document chunks."
)
B_TEXT = (
    "Currency exchange rates follow supply and demand while central banker "
    "decisions move the value of the american dollar rapidly."
)
A_QUERY = "How does DocMind perform owner-scoped semantic retrieval?"
B_QUERY = "What moves currency exchange rates?"


class FakeEmbeddingService:
    """Deterministic fixed-dimension embeddings (no model download).

    Each word is hashed into one of ``DIM`` buckets so every text embeds to
    the same dimension regardless of vocabulary growth and identical words
    always produce identical signals.
    """

    DIM = 64

    def __init__(self) -> None:
        self._seed = 0xCBF29CE484222325

    def _vector(self, text: str) -> list[int]:
        vector = [0] * self.DIM
        for word in text.lower().split():
            bucket = self._bucket(word) % self.DIM
            vector[bucket] += 1
        return vector

    def _bucket(self, word: str) -> int:
        value = self._seed
        for byte in word.encode("utf-8"):
            value ^= byte
            value = (value * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
        return value

    def generate_embeddings(self, texts: list[str]) -> list[list[int]]:
        return [self._vector(text) for text in texts]

    def get_embedding_dimension(self) -> int:
        return self.DIM


class RecordingProvider(BaseProvider):
    """A dependency-free BaseProvider that records the prompt it is given."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    @property
    def model(self) -> str:
        """Return the identifier of the provider's model."""
        return "test-model"

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
        images: list[dict] | None = None,
    ) -> str:
        self.prompts.append(prompt)
        return prompt


def _make_pdf(path: Path, text: str) -> None:
    """Write a one-page PDF containing the given text.

    ``insert_text`` truncates a line at the page edge, so the full text is
    laid out through ``insert_textbox`` which wraps it across lines instead.

    Args:
        path: The destination path for the PDF.
        text: The text to embed on the page.
    """
    document = fitz.open()
    page = document.new_page()
    rect = fitz.Rect(50, 50, 545, 700)
    page.insert_textbox(rect, text, fontsize=10)
    document.save(str(path))
    document.close()


def _norm(text: str) -> str:
    """Collapse all whitespace runs into single spaces.

    PDF text extraction can wrap a line at an arbitrary position, so chunk
    text is compared to the single-line source text in normalized form.

    Args:
        text: The raw text to normalize.

    Returns:
        The text with every whitespace run replaced by a single space.
    """
    return " ".join(text.split())


def _build_stack(tmp: Path):
    """Build an isolated, deterministic retrieval stack.

    Args:
        tmp: A temporary directory for the persisted stores.

    Returns:
        A tuple of the metadata store, the document registry, and a
        recording chat provider wired to the shared retriever.
    """
    embedding_service = FakeEmbeddingService()

    vector_store = VectorStore(dimension=embedding_service.get_embedding_dimension())
    metadata_store = MetadataStore()
    document_registry = DocumentRegistry(tmp / "documents.json")

    semantic = SemanticRetriever(
        embedding_service,
        vector_store,
        metadata_store,
        document_registry,
    )
    bm25 = BM25Retriever(metadata_store, document_registry)
    retriever = HybridRetriever(semantic_retriever=semantic, bm25_retriever=bm25)

    chat_provider = RecordingProvider()
    chat_service = ChatService(
        retriever,
        PromptBuilder(),
        _ProviderManagerAdapter([chat_provider]),
    )

    return (
        embedding_service,
        vector_store,
        metadata_store,
        document_registry,
        retriever,
        chat_service,
        chat_provider,
    )


class _ProviderManagerAdapter:
    """Minimal in-memory provider manager used to drive ChatService."""

    def __init__(self, providers: list) -> None:
        self._provider = providers[0]

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
        images: list[dict] | None = None,
    ):
        from app.models.llm import LLMResponse

        text = await self._provider.generate(
            prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            images=images,
        )
        return LLMResponse(text=text, provider="RecordingProvider", model=self._provider.model)


class _FakeDocumentService:
    """Stand-in for DocumentService driving the real pipeline plus test stores.

    Reads the current dependency overrides on every call so it always writes
    into the exact stores the shared retriever resolves, even after the
    dependency caches are cleared.
    """

    def __init__(self) -> None:
        self._processor = PDFProcessor()
        self._chunker = Chunker(chunk_size=10000, chunk_overlap=200)

    def _embedding_service(self):
        return app.dependency_overrides[get_embedding_service]()

    def _vector_store(self):
        return app.dependency_overrides[get_vector_store]()

    def _metadata_store(self):
        return app.dependency_overrides[get_metadata_store]()

    def capture_state(self):
        """Return a no-op snapshot (this fake never fails an upload)."""

    def restore_state(self, snapshot) -> None:
        """No-op restore (this fake never mutates shared state)."""

    async def index_document(
        self,
        file_path: str,
        workspace_id: str = DEFAULT_WORKSPACE,
        document_id: str | None = None,
        owner_id: str = "",
        filename: str | None = None,
    ):
        from app.services.document import IndexDocumentResult
        from app.services.text_cleaner import clean_text

        text = self._processor.extract_text(file_path)
        cleaned = clean_text(text)
        chunks = self._chunker.chunk(cleaned)
        embedding_service = self._embedding_service()
        vector_store = self._vector_store()
        metadata_store = self._metadata_store()
        embeddings = embedding_service.generate_embeddings(chunks)
        vector_store.add_embeddings(embeddings)
        metadata_store.add_documents(
            chunks,
            Path(file_path).name,
            workspace_id,
            document_id,
            owner_id,
        )
        return IndexDocumentResult(
            filename=filename or Path(file_path).name,
            total_chunks=len(chunks),
            total_embeddings=len(embeddings),
            status="indexed",
        )


def _run_scenario(check) -> None:
    """Run all owner-scoped retrieval/chat wiring checks.

    Args:
        check: The check-registration callable.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        stack = _build_stack(tmp)
        (
            _embedding_service,
            _vector_store,
            metadata_store,
            document_registry,
            retriever,
            chat_service,
            chat_provider,
        ) = stack

        _clear_caches()
        app.dependency_overrides[get_auth_service] = lambda: AuthService(
            users=JsonUserRepository(tmp / "users.json"),
            passwords=PasswordService(),
            tokens=JWTService(secret_key=TOKEN_SECRET),
        )
        app.dependency_overrides[get_embedding_service] = (
            lambda: _embedding_service
        )
        app.dependency_overrides[get_vector_store] = lambda: _vector_store
        app.dependency_overrides[get_metadata_store] = lambda: metadata_store
        app.dependency_overrides[get_document_registry] = (
            lambda: document_registry
        )
        app.dependency_overrides[get_document_repository] = (
            lambda: JsonDocumentRepository(document_registry)
        )
        app.dependency_overrides[get_document_service] = (
            lambda: _FakeDocumentService()
        )
        app.dependency_overrides[get_retriever] = lambda: retriever
        app.dependency_overrides[get_chat_service] = lambda: chat_service

        auth_service = app.dependency_overrides[get_auth_service]()
        token_service = JWTService(secret_key=TOKEN_SECRET)
        user_a = auth_service.register("owner.a@example.com", PASSWORD)
        user_b = auth_service.register("owner.b@example.com", PASSWORD)
        token_a = token_service.create_access_token(user_a.user_id)
        token_b = token_service.create_access_token(user_b.user_id)

        try:
            with TestClient(app) as client:
                bearer_a = {"Authorization": f"Bearer {token_a}"}
                bearer_b = {"Authorization": f"Bearer {token_b}"}

                pdf_a = tmp / "docmind.pdf"
                pdf_b = tmp / "finance.pdf"
                _make_pdf(pdf_a, A_TEXT)
                _make_pdf(pdf_b, B_TEXT)

                upload_a = client.post(
                    "/documents/upload",
                    headers=bearer_a,
                    files={"file": ("docmind.pdf", pdf_a.read_bytes(), "application/pdf")},
                )
                upload_b = client.post(
                    "/documents/upload",
                    headers=bearer_b,
                    files={"file": ("finance.pdf", pdf_b.read_bytes(), "application/pdf")},
                )
                check(
                    "A. A and B documents upload successfully",
                    upload_a.status_code == 200 and upload_b.status_code == 200,
                    f"a={upload_a.status_code}, b={upload_b.status_code}",
                )

                a_doc_id = upload_a.json().get("data", {}).get("document_id")
                b_doc_id = upload_b.json().get("data", {}).get("document_id")

                check(
                    "A. registries record the correct owners",
                    bool(a_doc_id) and bool(b_doc_id)
                    and document_registry.get_document(a_doc_id, user_a.user_id) is not None
                    and document_registry.get_document(b_doc_id, user_a.user_id) is None
                    and document_registry.get_document(b_doc_id, user_b.user_id) is not None,
                )

                retrieve_a = client.post(
                    "/retrieve", json={"query": B_QUERY}, headers=bearer_a
                )
                check(
                    "B. owner A /retrieve excludes B's chunk",
                    retrieve_a.status_code == 200
                    and all(_norm(B_TEXT) not in _norm(str(chunk.get("text", ""))) for chunk in retrieve_a.json().get("data", {}).get("results", [])),
                    f"status={retrieve_a.status_code}, results={len(retrieve_a.json().get('data', {}).get('results', []))}",
                )

                retrieve_b = client.post(
                    "/retrieve", json={"query": B_QUERY}, headers=bearer_b
                )
                check(
                    "C. owner B /retrieve returns B's chunk",
                    retrieve_b.status_code == 200
                    and any(_norm(B_TEXT) in _norm(str(chunk.get("text", ""))) for chunk in retrieve_b.json().get("data", {}).get("results", [])),
                    f"status={retrieve_b.status_code}",
                )

                chat_a = client.post(
                    "/chat/", data={"question": "summarize docmind.pdf"}, headers=bearer_a
                )
                prompt_a = chat_provider.prompts[-1] if chat_provider.prompts else ""
                check(
                    "D. owner A /chat context excludes B's chunk",
                    chat_a.status_code == 200
                    and _norm(B_TEXT) not in _norm(prompt_a),
                    f"status={chat_a.status_code}",
                )

                chat_b = client.post(
                    "/chat/", data={"question": "summarize finance.pdf"}, headers=bearer_b
                )
                prompt_b = chat_provider.prompts[-1] if chat_provider.prompts else ""
                check(
                    "E. owner B /chat context uses B's chunk",
                    chat_b.status_code == 200
                    and _norm(B_TEXT) in _norm(prompt_b),
                    f"status={chat_b.status_code}",
                )

                check(
                    "F. missing auth -> 401 on /retrieve",
                    client.post("/retrieve", json={"query": "hi"}).status_code == 401,
                )
                check(
                    "F. missing auth -> 401 on /chat",
                    client.post("/chat/", json={"question": "hi"}).status_code == 401,
                )
                check(
                    "F. invalid auth -> 401 on /retrieve",
                    client.post(
                        "/retrieve",
                        json={"query": "hi"},
                        headers={"Authorization": "Bearer not.a.jwt"},
                    ).status_code == 401,
                )
                check(
                    "F. invalid auth -> 401 on /chat",
                    client.post(
                        "/chat/",
                        json={"question": "hi"},
                        headers={"Authorization": "Bearer not.a.jwt"},
                    ).status_code == 401,
                )
        finally:
            app.dependency_overrides.clear()
            # FastAPI resolves cached dependency singletons once per process;
            # kill the caches so the scenario's overrides are used instead of
            # the real singletons (which may have been built by earlier runs).
            _clear_caches()


def _clear_caches() -> None:
    """Invalidate cached dependency singletons so overrides are re-resolved."""
    for getter in (
        get_auth_service,
        get_chat_service,
        get_document_registry,
        get_document_repository,
        get_document_service,
        get_embedding_service,
        get_metadata_store,
        get_retriever,
        get_vector_store,
    ):
        cache_clear = getattr(getter, "cache_clear", None)
        if cache_clear is not None:
            cache_clear()


def main() -> int:
    """Run all API ownership wiring checks and return the exit code.

    Returns:
        0 when all checks pass, otherwise 1.
    """
    print("=" * 60)
    print("Retrieval Ownership API Test")
    print("=" * 60)

    check_results: list[bool] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        status = "[OK]" if passed else "[FAIL]"
        print(f"{status} {name}" + (f" - {detail}" if detail else ""))
        check_results.append(passed)

    _run_scenario(check)

    print("\n" + "=" * 60)
    all_passed = all(check_results)
    print(f"Retrieval Ownership API Test {'PASSED' if all_passed else 'FAILED'}")
    print("=" * 60)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())