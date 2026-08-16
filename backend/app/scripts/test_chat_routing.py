"""Deterministic regression test for chat query routing.

Verifies, without any network or live LLM calls:

- classification of representative queries into GENERAL / DOCUMENT / METADATA
- general queries do not call the retriever
- metadata queries do not call the retriever or the LLM
- document queries preserve the existing retrieval + grounded-prompt flow

Usage (from backend/):
    PYTHONPATH=. ../.venv/bin/python app/scripts/test_chat_routing.py
"""

import asyncio
import hashlib

from app.services.chat.chat_service import ChatService
from app.services.chat.query_router import QueryCategory, QueryRouter
from app.services.document_registry import Document
from app.services.llm.prompt_builder import PromptBuilder
from app.services.llm.provider_manager import ProviderManager
from app.services.llm.providers.base import BaseProvider

CONTEXT_TEXT = (
    "Anukul Chandra is an AI / ML Engineer from Dhaka, Bangladesh."
)

_EMBEDDING_DIM = 512


class FakeEmbeddingService:
    """Deterministic embedding service using hashed character trigrams.

    Mirrors the real ``EmbeddingService`` interface (``generate_embeddings``)
    while staying deterministic and dependency-free. Whole strings are hashed
    as character trigrams into a wide bucket space, so typo-laden queries land
    near their correctly spelled counterparts (most trigrams survive a single
    typo) while unrelated text stays far from the document/metadata centroids.
    """

    def __init__(self) -> None:
        self.calls = 0

    def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        vectors: list[list[float]] = []
        for text in texts:
            vector = [0.0] * _EMBEDDING_DIM
            lowered = text.lower()
            for index in range(max(0, len(lowered) - 2)):
                trigram = lowered[index : index + 3]
                bucket = int(hashlib.md5(trigram.encode()).hexdigest(), 16) % _EMBEDDING_DIM
                vector[bucket] += 1.0
            vectors.append(vector)
        return vectors


def build_semantic_router() -> tuple[QueryRouter, FakeEmbeddingService]:
    """Build a router with the deterministic fake embedding service."""
    embedding_service = FakeEmbeddingService()
    return QueryRouter(embedding_service), embedding_service


class RecordingRetriever:
    """Records whether retrieval was invoked and returns a fixed context."""

    def __init__(self) -> None:
        self.calls = 0

    def retrieve(self, question: str, owner_id: str = "") -> list[dict]:
        self.calls += 1
        return [
            {
                "text": CONTEXT_TEXT,
                "filename": "Anukul Chandra-CV.pdf",
                "chunk_id": 1,
            }
        ]


class RecordingProvider(BaseProvider):
    """Records every prompt it receives and returns a fixed answer."""

    def __init__(self) -> None:
        self._model = "mock/provider"
        self.prompts: list[str] = []

    @property
    def model(self) -> str:
        return self._model

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> str:
        self.prompts.append(prompt)
        return "mock answer"


class FakeDocumentRepository:
    """Deterministic document repository for the metadata path."""

    def __init__(self, documents: list[Document] | None = None) -> None:
        self._documents = documents or []

    def list_documents(self, owner_id: str) -> list[Document]:
        return [
            document
            for document in self._documents
            if document.owner_id == owner_id and not document.deleted
        ]


def make_document(filename: str, owner_id: str, deleted: bool = False) -> Document:
    """Build a Document record for testing."""
    return Document(
        document_id=f"doc-{filename}",
        workspace_id="default",
        filename=filename,
        uploaded_at="2026-01-01T00:00:00Z",
        chunk_count=1,
        deleted=deleted,
        owner_id=owner_id,
    )


async def test_classification() -> bool:
    """Queries map to the intended routing categories."""
    router = QueryRouter()
    expected = {
        "Hello": QueryCategory.GENERAL,
        "What is RAG?": QueryCategory.GENERAL,
        "Explain machine learning": QueryCategory.GENERAL,
        "What is in my CV?": QueryCategory.DOCUMENT,
        "Based on my CV, what roles suit me?": QueryCategory.DOCUMENT,
        "What is the main topic of my documents?": QueryCategory.DOCUMENT,
        "What documents have I uploaded?": QueryCategory.METADATA,
        "How many documents have I uploaded?": QueryCategory.METADATA,
        "Which documents do I have?": QueryCategory.METADATA,
        "List my documents": QueryCategory.METADATA,
    }
    for question, category in expected.items():
        actual = router.classify(question)
        if actual is not category:
            print(f"FAIL: {question!r} -> {actual.value}, expected {category.value}")
            return False
    return True


async def test_document_reference_classification() -> bool:
    """Explicit document references are classified as DOCUMENT."""
    router = QueryRouter()
    references = [
        "give me the summary of Anukul-chandra Cv.pdf",
        "summarize Anukul-chandra Cv.pdf",
        "summarize my resume.docx",
        "what does Anukul-chandra Cv.pdf say?",
        "what does notes.txt say?",
        "according to Anukul-chandra Cv.pdf, what is the main topic?",
        "according to the report.md, what were the findings?",
        "summarize that file",
        "summarize this document",
        "what does the document say about Anukul?",
        "explain the file I just uploaded",
    ]
    for question in references:
        actual = router.classify(question)
        if actual is not QueryCategory.DOCUMENT:
            print(
                f"FAIL: {question!r} -> {actual.value}, expected "
                f"{QueryCategory.DOCUMENT.value}"
            )
            return False
    return True


def build_service(
    retriever: RecordingRetriever,
    provider: RecordingProvider,
    repository: FakeDocumentRepository | None = None,
) -> ChatService:
    """Build a ChatService wired to the recording fakes."""
    return ChatService(
        retriever,
        PromptBuilder(),
        ProviderManager([provider]),
        document_repository=repository,
    )


async def test_general_skips_retrieval() -> bool:
    """General queries reach the LLM without any retrieval."""
    for question in ("Hello", "What is RAG?"):
        retriever = RecordingRetriever()
        provider = RecordingProvider()
        service = build_service(retriever, provider)

        response = await service.chat(question, owner_id="owner-1")

        if retriever.calls != 0:
            print(f"FAIL: {question!r} triggered retrieval ({retriever.calls} calls)")
            return False
        if len(provider.prompts) != 1:
            print(f"FAIL: {question!r} did not reach the LLM exactly once")
            return False
        if "Context:" in provider.prompts[0]:
            print(f"FAIL: general prompt should have no context block: {provider.prompts[0]!r}")
            return False
        if response.text != "mock answer":
            print("FAIL: unexpected response text")
            return False
    return True


async def test_metadata_skips_retrieval_and_llm() -> bool:
    """Metadata queries answer from the repository without retrieval or an LLM."""
    repository = FakeDocumentRepository(
        [
            make_document("Anukul Chandra-CV.pdf", "owner-1"),
            make_document("2112.13047v1.pdf", "owner-1"),
            make_document("deleted.pdf", "owner-1", deleted=True),
        ]
    )
    retriever = RecordingRetriever()
    provider = RecordingProvider()
    service = build_service(retriever, provider, repository)

    response = await service.chat("What documents have I uploaded?", owner_id="owner-1")

    if retriever.calls != 0:
        print("FAIL: metadata query triggered retrieval")
        return False
    if provider.prompts:
        print("FAIL: metadata query called the LLM")
        return False
    if response.provider != "metadata":
        print(f"FAIL: expected provider 'metadata', got {response.provider!r}")
        return False
    if "2 uploaded documents" not in response.text:
        print(f"FAIL: expected document count in answer, got {response.text!r}")
        return False
    if "Anukul Chandra-CV.pdf" not in response.text or "2112.13047v1.pdf" not in response.text:
        print(f"FAIL: expected filenames in answer, got {response.text!r}")
        return False
    if "deleted.pdf" in response.text:
        print(f"FAIL: deleted document should be omitted, got {response.text!r}")
        return False
    return True


async def test_metadata_empty() -> bool:
    """A user with no documents gets a clear empty-state answer."""
    service = build_service(
        RecordingRetriever(),
        RecordingProvider(),
        FakeDocumentRepository([]),
    )

    response = await service.chat("What documents have I uploaded?", owner_id="owner-1")

    if "no uploaded documents" not in response.text:
        print(f"FAIL: expected empty-state answer, got {response.text!r}")
        return False
    return True


async def test_document_uses_rag_flow() -> bool:
    """Document questions use retrieval and the grounded prompt."""
    retriever = RecordingRetriever()
    provider = RecordingProvider()
    service = build_service(retriever, provider)

    response = await service.chat("What is in my CV?", owner_id="owner-1")

    if retriever.calls != 1:
        print(f"FAIL: expected one retrieval call, got {retriever.calls}")
        return False
    if len(provider.prompts) != 1:
        print("FAIL: expected exactly one LLM call")
        return False
    prompt = provider.prompts[0]
    if "Context:" not in prompt:
        print("FAIL: document prompt must contain a context block")
        return False
    if CONTEXT_TEXT not in prompt:
        print("FAIL: retrieved context must be delivered to the LLM")
        return False
    if response.text != "mock answer":
        print("FAIL: unexpected response text")
        return False
    return True


async def test_mixed_uses_rag_flow() -> bool:
    """Mixed questions (document anchor + general ask) use the RAG flow."""
    retriever = RecordingRetriever()
    provider = RecordingProvider()
    service = build_service(retriever, provider)

    response = await service.chat("Based on my CV, what roles suit me?", owner_id="owner-1")

    if retriever.calls != 1:
        print(f"FAIL: expected one retrieval call, got {retriever.calls}")
        return False
    if "Context:" not in provider.prompts[0]:
        print("FAIL: mixed prompt must contain a context block")
        return False
    if response.text != "mock answer":
        print("FAIL: unexpected response text")
        return False
    return True


async def test_semantic_typo_metadata() -> bool:
    """Typo-laden metadata questions are routed to METADATA via embeddings."""
    router, _ = build_semantic_router()
    typo_queries = [
        "which dcuments i upload in here?",
        "how many docs have i uploadd?",
        "list mi documents plz",
        "wut documnts r in my account?",
    ]
    for question in typo_queries:
        actual = router.classify(question)
        if actual is not QueryCategory.METADATA:
            print(
                f"FAIL: {question!r} -> {actual.value}, expected "
                f"{QueryCategory.METADATA.value}"
            )
            return False
    return True


async def test_semantic_typo_document() -> bool:
    """Typo-laden document questions are routed to DOCUMENT via embeddings."""
    router, _ = build_semantic_router()
    typo_queries = [
        "summarize mi resume plz",
        "what iz in mi cv?",
        "wats the main topic of my documents?",
    ]
    for question in typo_queries:
        actual = router.classify(question)
        if actual is not QueryCategory.DOCUMENT:
            print(
                f"FAIL: {question!r} -> {actual.value}, expected "
                f"{QueryCategory.DOCUMENT.value}"
            )
            return False
    return True


async def test_semantic_general() -> bool:
    """Normal general questions remain GENERAL via embeddings."""
    router, _ = build_semantic_router()
    general_queries = [
        "hello there, how are you?",
        "tell me about deep learning",
        "what is the weather today",
        "tell me a joke please",
    ]
    for question in general_queries:
        actual = router.classify(question)
        if actual is not QueryCategory.GENERAL:
            print(
                f"FAIL: {question!r} -> {actual.value}, expected "
                f"{QueryCategory.GENERAL.value}"
            )
            return False
    return True


async def test_deterministic_rules_take_precedence() -> bool:
    """Deterministic matches win without consulting the embedding service."""
    router, embedding_service = build_semantic_router()

    cases = [
        ("list my documents please", QueryCategory.METADATA),
        ("summarize Anukul-chandra Cv.pdf", QueryCategory.DOCUMENT),
        ("What is in my CV?", QueryCategory.DOCUMENT),
        ("What documents have I uploaded?", QueryCategory.METADATA),
    ]
    for question, expected in cases:
        embedding_service.calls = 0
        actual = router.classify(question)
        if actual is not expected:
            print(
                f"FAIL: {question!r} -> {actual.value}, expected {expected.value}"
            )
            return False
        if embedding_service.calls != 0:
            print(
                f"FAIL: deterministic {question!r} still called embeddings "
                f"({embedding_service.calls} calls)"
            )
            return False
    return True


async def test_semantic_ambiguous() -> bool:
    """Ambiguous questions still resolve to a confident category, not GENERAL."""
    router, _ = build_semantic_router()
    ambiguous = [
        "wats the main topic of my documents?",
        "give me the lowdown on my docs",
        "whats in the documnts i got",
    ]
    for question in ambiguous:
        actual = router.classify(question)
        if actual is QueryCategory.GENERAL:
            print(f"FAIL: ambiguous {question!r} fell back to GENERAL")
            return False
    return True


async def test_semantic_low_confidence_is_general() -> bool:
    """Queries far from every centroid stay GENERAL."""
    router, _ = build_semantic_router()
    low_confidence = [
        "zzzz qqqq xxxx vvvv",
        "hurricane aetherion economics 42",
    ]
    for question in low_confidence:
        actual = router.classify(question)
        if actual is not QueryCategory.GENERAL:
            print(
                f"FAIL: low-confidence {question!r} -> {actual.value}, "
                f"expected {QueryCategory.GENERAL.value}"
            )
            return False
    return True


async def test_router_without_embeddings_is_deterministic() -> bool:
    """Without an embedding service the router stays purely deterministic."""
    router = QueryRouter()
    cases = [
        ("which dcuments i upload in here?", QueryCategory.GENERAL),
        ("Hello", QueryCategory.GENERAL),
        ("List my documents", QueryCategory.METADATA),
        ("What is in my CV?", QueryCategory.DOCUMENT),
    ]
    for question, expected in cases:
        actual = router.classify(question)
        if actual is not expected:
            print(
                f"FAIL: {question!r} -> {actual.value}, expected {expected.value}"
            )
            return False
    return True


async def main() -> None:
    """Run all routing scenarios and report the overall result."""
    print("=" * 60)
    print("Chat Query Routing Test")
    print("=" * 60)

    scenarios = [
        ("Classification: GENERAL/DOCUMENT/METADATA", test_classification),
        ("Classification: document references -> DOCUMENT", test_document_reference_classification),
        ("GENERAL: no retrieval, plain prompt", test_general_skips_retrieval),
        ("METADATA: no retrieval, no LLM, lists docs", test_metadata_skips_retrieval_and_llm),
        ("METADATA: empty state", test_metadata_empty),
        ("DOCUMENT: retrieval + grounded prompt", test_document_uses_rag_flow),
        ("MIXED: retrieval + grounded prompt", test_mixed_uses_rag_flow),
        ("SEMANTIC: typo metadata -> METADATA", test_semantic_typo_metadata),
        ("SEMANTIC: typo document -> DOCUMENT", test_semantic_typo_document),
        ("SEMANTIC: general stays GENERAL", test_semantic_general),
        ("SEMANTIC: deterministic takes precedence", test_deterministic_rules_take_precedence),
        ("SEMANTIC: ambiguous stays confident", test_semantic_ambiguous),
        ("SEMANTIC: low confidence -> GENERAL", test_semantic_low_confidence_is_general),
        ("ROUTER: no embeddings = deterministic", test_router_without_embeddings_is_deterministic),
    ]

    passed = True
    for label, scenario in scenarios:
        print()
        print(label)
        result = await scenario()
        print("PASSED" if result else "FAILED")
        passed = passed and result

    print()
    print("=" * 60)
    print(f"Chat Routing Test {'PASSED' if passed else 'FAILED'}")
    print("=" * 60)
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())