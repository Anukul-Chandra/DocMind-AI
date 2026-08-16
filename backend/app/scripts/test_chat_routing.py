"""Deterministic regression test for chat query routing.

Verifies, without any network or live LLM calls:

- classification of representative queries into GENERAL / DOCUMENT / METADATA
- general queries do not call the retriever
- metadata queries do not call the retriever or the LLM
- metadata typos ("dcuments", "documnts", "uploadd") resolve to METADATA
- document queries preserve the existing retrieval + grounded-prompt flow
- the hybrid relevance gate:
  - routes self-referential / self-attribute questions to RAG using the low
    personal floor
  - rescues document-noun questions with positive BM25 evidence
  - keeps generic ML/AI topical questions on the general path via the high
    topic threshold
  - keeps empty-corpus questions GENERAL
  - scopes to the owner
  - reuses the query embedding for retrieval
- deterministic metadata / explicit-filename rules always take precedence
  over the relevance gate

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

_PERSONAL_FLOOR = 0.07
_TOPIC_THRESHOLD = 0.45
_DOCNOUN_FLOOR = 0.15


class FakeEmbeddingService:
    """Deterministic embedding service using hashed character trigrams.

    Mirrors the real ``EmbeddingService`` interface (``generate_embeddings``)
    while staying deterministic and dependency-free. Used to verify that the
    router embeds the question exactly once and reuses the vector.
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


class FakeRelevanceScorer:
    """Deterministic relevance gate stand-in for the semantic retriever.

    Records every invocation (question, owner id, query embedding) and returns
    a per-query score, defaulting to ``default`` when a query has no entry.
    This models the real gate (``SemanticRetriever.best_similarity``) so the
    router logic - thresholding, owner scoping, precedence, embedding reuse -
    can be verified without an embedding model.
    """

    def __init__(self, default: float = 0.0) -> None:
        self.default = default
        self.scores: dict[str, float] = {}
        self.calls: list[tuple[str, str, list[float] | None]] = []

    def __call__(
        self,
        question: str,
        owner_id: str,
        query_embedding: list[float] | None = None,
    ) -> float:
        self.calls.append((question, owner_id, query_embedding))
        return self.scores.get(question, self.default)


class FakeLexicalScorer:
    """Deterministic BM25 stand-in for the router's lexical scorer.

    Records every invocation (question, owner id) and returns a per-query
    score, defaulting to ``default`` when a query has no entry. This models
    ``BM25Retriever.best_score`` so the document-noun rescue branch and the
    personal-attribute branch can be verified without a real BM25 index.
    """

    def __init__(self, default: float = 0.0) -> None:
        self.default = default
        self.scores: dict[str, float] = {}
        self.calls: list[tuple[str, str]] = []

    def __call__(self, question: str, owner_id: str) -> float:
        self.calls.append((question, owner_id))
        return self.scores.get(question, self.default)


def build_semantic_router() -> tuple[QueryRouter, FakeEmbeddingService, FakeRelevanceScorer, FakeLexicalScorer]:
    """Build a router with deterministic embedding, semantic, and lexical fakes."""
    embedding_service = FakeEmbeddingService()
    scorer = FakeRelevanceScorer()
    lexical = FakeLexicalScorer()
    router = QueryRouter(
        embedding_service,
        relevance_scorer=scorer,
        lexical_scorer=lexical,
        personal_floor=_PERSONAL_FLOOR,
        topic_threshold=_TOPIC_THRESHOLD,
        docnoun_floor=_DOCNOUN_FLOOR,
    )
    return router, embedding_service, scorer, lexical


class RecordingRetriever:
    """Records whether retrieval was invoked and returns a fixed context."""

    def __init__(self) -> None:
        self.calls = 0
        self.last_query_embedding: list[float] | None = None

    def retrieve(
        self,
        question: str,
        owner_id: str = "",
        query_embedding: list[float] | None = None,
    ) -> list[dict]:
        self.calls += 1
        self.last_query_embedding = query_embedding
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
    """Deterministic queries map to the intended routing categories."""
    router = QueryRouter()
    expected = {
        "Hello": QueryCategory.GENERAL,
        "What is RAG?": QueryCategory.GENERAL,
        "Explain machine learning": QueryCategory.GENERAL,
        "What documents have I uploaded?": QueryCategory.METADATA,
        "How many documents have I uploaded?": QueryCategory.METADATA,
        "Which documents do I have?": QueryCategory.METADATA,
        "List my documents": QueryCategory.METADATA,
        "summarize Anukul-chandra Cv.pdf": QueryCategory.DOCUMENT,
    }
    for question, category in expected.items():
        actual = router.classify(question)
        if actual is not category:
            print(f"FAIL: {question!r} -> {actual.value}, expected {category.value}")
            return False
    return True


async def test_document_reference_classification() -> bool:
    """Explicit document filename references are classified as DOCUMENT."""
    router = QueryRouter()
    references = [
        "give me the summary of Anukul-chandra Cv.pdf",
        "summarize Anukul-chandra Cv.pdf",
        "summarize my resume.docx",
        "what does Anukul-chandra Cv.pdf say?",
        "what does notes.txt say?",
        "according to Anukul-chandra Cv.pdf, what is the main topic?",
        "according to the report.md, what were the findings?",
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
    query_router: QueryRouter | None = None,
) -> ChatService:
    """Build a ChatService wired to the recording fakes."""
    return ChatService(
        retriever,
        PromptBuilder(),
        ProviderManager([provider]),
        document_repository=repository,
        query_router=query_router,
    )


async def test_general_skips_retrieval() -> bool:
    """General queries reach the LLM without any retrieval."""
    for question in ("Hello", "What is RAG?"):
        router, _, scorer, _ = build_semantic_router()
        retriever = RecordingRetriever()
        provider = RecordingProvider()
        service = build_service(retriever, provider, query_router=router)

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
    router, _, scorer, _ = build_semantic_router()
    scorer.scores = {"What is in my CV?": 0.45}
    retriever = RecordingRetriever()
    provider = RecordingProvider()
    service = build_service(retriever, provider, query_router=router)

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
    router, _, scorer, _ = build_semantic_router()
    scorer.scores = {"Based on my CV, what roles suit me?": 0.48}
    retriever = RecordingRetriever()
    provider = RecordingProvider()
    service = build_service(retriever, provider, query_router=router)

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


async def test_gate_implicit_document_questions() -> bool:
    """Self-referential personal / document questions route to RAG on the low floor."""
    router, embedding_service, scorer, _ = build_semantic_router()
    scorer.scores = {
        "What is in my CV?": 0.35,
        "what is my educational background?": 0.33,
        "what was my last job?": 0.31,
        "summarize my work experience": 0.30,
        "tell me about my education": 0.17,
        "where did I study?": 0.08,
    }
    for question in scorer.scores:
        actual = router.classify(question, owner_id="owner-1")
        if actual is not QueryCategory.DOCUMENT:
            print(
                f"FAIL: implicit document {question!r} -> {actual.value}, "
                f"expected {QueryCategory.DOCUMENT.value}"
            )
            return False
        if embedding_service.calls != 1:
            print(f"FAIL: {question!r} should embed the question exactly once")
            return False
        embedding_service.calls = 0
    return True


async def test_gate_self_attribute_questions() -> bool:
    """Personal self-attribute questions (education, phone, location) use the low floor."""
    router, _, scorer, _ = build_semantic_router()
    scorer.scores = {
        "my phone number": 0.18,
        "where do I live?": 0.11,
        "what is my email?": 0.27,
        "what skills do i have?": 0.33,
        "tell me about my education": 0.17,
    }
    for question in scorer.scores:
        actual = router.classify(question, owner_id="owner-1")
        if actual is not QueryCategory.DOCUMENT:
            print(
                f"FAIL: self-attribute {question!r} -> {actual.value}, "
                f"expected {QueryCategory.DOCUMENT.value}"
            )
            return False
    return True


async def test_gate_personal_with_lexical_evidence() -> bool:
    """Personal questions without a self-attribute need positive BM25 evidence."""
    router, _, scorer, lexical = build_semantic_router()
    scorer.scores = {"what was my prevous job?": 0.20}
    lexical.scores = {"what was my prevous job?": 4.0}
    actual = router.classify("what was my prevous job?", owner_id="owner-1")
    if actual is not QueryCategory.DOCUMENT:
        print(
            f"FAIL: personal+lexical {actual.value}, "
            f"expected {QueryCategory.DOCUMENT.value}"
        )
        return False
    return True


async def test_gate_paraphrase_and_typo() -> bool:
    """Paraphrased and typo-laden personal document questions route to RAG."""
    router, _, scorer, lexical = build_semantic_router()
    scorer.scores = {
        "summarize my resume": 0.32,
        "tell me about your professional background": 0.30,
        "summarize mi resume plz": 0.24,
    }
    lexical.scores = {
        "summarize my resume": 5.0,
        "tell me about your professional background": 4.0,
        "summarize mi resume plz": 5.0,
    }
    for question in scorer.scores:
        actual = router.classify(question, owner_id="owner-1")
        if actual is not QueryCategory.DOCUMENT:
            print(
                f"FAIL: paraphrase/typo {question!r} -> {actual.value}, "
                f"expected {QueryCategory.DOCUMENT.value}"
            )
            return False
    return True


async def test_gate_document_noun_rescue() -> bool:
    """A document-noun question rescues low semantic scores with BM25 evidence."""
    router, _, scorer, lexical = build_semantic_router()
    scorer.scores = {"what method does the paper use?": 0.18}
    lexical.scores = {"what method does the paper use?": 7.0}
    actual = router.classify("what method does the paper use?", owner_id="owner-1")
    if actual is not QueryCategory.DOCUMENT:
        print(
            f"FAIL: document-noun rescue {actual.value}, "
            f"expected {QueryCategory.DOCUMENT.value}"
        )
        return False
    # Without BM25 evidence the same low semantic score stays GENERAL.
    scorer.scores = {"what method does the paper use?": 0.18}
    lexical.scores = {}
    actual = router.classify("what method does the paper use?", owner_id="owner-1")
    if actual is not QueryCategory.GENERAL:
        print(
            f"FAIL: document-noun without BM25 -> {actual.value}, "
            f"expected GENERAL"
        )
        return False
    return True


async def test_gate_topic_questions_stay_general() -> bool:
    """Generic ML/AI topical questions stay GENERAL despite high semantic scores."""
    router, _, scorer, lexical = build_semantic_router()
    scorer.scores = {
        "define machine learning": 0.35,
        "what is deep learning?": 0.41,
        "history of AI": 0.39,
    }
    lexical.scores = {
        "define machine learning": 5.0,
        "what is deep learning?": 5.0,
        "history of AI": 6.0,
    }
    for question in scorer.scores:
        actual = router.classify(question, owner_id="owner-1")
        if actual is not QueryCategory.GENERAL:
            print(
                f"FAIL: topic question {question!r} -> {actual.value}, "
                f"expected {QueryCategory.GENERAL.value}"
            )
            return False
    return True


async def test_gate_unrelated_general() -> bool:
    """Unrelated general questions stay GENERAL below threshold."""
    router, _, scorer, _ = build_semantic_router()
    scorer.default = 0.10
    general_queries = [
        "hello there, how are you?",
        "what is the weather today",
        "tell me a joke please",
        "what is the capital of france?",
    ]
    for question in general_queries:
        actual = router.classify(question, owner_id="owner-1")
        if actual is not QueryCategory.GENERAL:
            print(
                f"FAIL: general {question!r} -> {actual.value}, "
                f"expected {QueryCategory.GENERAL.value}"
            )
            return False
    return True


async def test_gate_topic_threshold_boundary() -> bool:
    """Generic topics below the topic threshold stay GENERAL; above route to RAG."""
    router, _, scorer, _ = build_semantic_router()
    scorer.scores = {
        "generic topic just below": _TOPIC_THRESHOLD - 0.01,
        "generic topic at threshold": _TOPIC_THRESHOLD,
        "generic topic just above": _TOPIC_THRESHOLD + 0.01,
    }
    expected = {
        "generic topic just below": QueryCategory.GENERAL,
        "generic topic at threshold": QueryCategory.DOCUMENT,
        "generic topic just above": QueryCategory.DOCUMENT,
    }
    for question, category in expected.items():
        actual = router.classify(question, owner_id="owner-1")
        if actual is not category:
            print(
                f"FAIL: {question!r} -> {actual.value}, expected {category.value}"
            )
            return False
    return True


async def test_gate_personal_floor_boundary() -> bool:
    """Personal self-attribute questions use the low floor; bare personal needs lexical."""
    router, _, scorer, lexical = build_semantic_router()
    scorer.scores = {
        "my education": _PERSONAL_FLOOR,
        "my education low": _PERSONAL_FLOOR - 0.01,
    }
    expected = {
        "my education": QueryCategory.DOCUMENT,
        "my education low": QueryCategory.GENERAL,
    }
    for question, category in expected.items():
        actual = router.classify(question, owner_id="owner-1")
        if actual is not category:
            print(
                f"FAIL: {question!r} -> {actual.value}, expected {category.value}"
            )
            return False
    # A bare personal reference (no self-attribute) with low semantic and no
    # lexical evidence stays GENERAL.
    scorer.scores = {"where did i go?": 0.10}
    lexical.scores = {}
    actual = router.classify("where did i go?", owner_id="owner-1")
    if actual is not QueryCategory.GENERAL:
        print(f"FAIL: bare personal no-evidence -> {actual.value}, expected GENERAL")
        return False
    return True


async def test_gate_empty_corpus_is_general() -> bool:
    """A user with an empty corpus gets GENERAL, not RAG."""
    router, _, scorer, lexical = build_semantic_router()
    scorer.default = 0.0
    lexical.default = 0.0
    questions = [
        "What is in my CV?",
        "summarize my resume",
        "what is my educational background?",
    ]
    for question in questions:
        actual = router.classify(question, owner_id="owner-1")
        if actual is not QueryCategory.GENERAL:
            print(
                f"FAIL: empty-corpus {question!r} -> {actual.value}, "
                f"expected {QueryCategory.GENERAL.value}"
            )
            return False
    return True


async def test_gate_owner_scoping() -> bool:
    """The owner id is passed through to the relevance and lexical gates."""
    router, _, scorer, lexical = build_semantic_router()
    scorer.scores = {"What is in my CV?": 0.45}
    router.classify("What is in my CV?", owner_id="owner-42")
    if not scorer.calls:
        print("FAIL: relevance gate was never consulted")
        return False
    recorded_owner = scorer.calls[0][1]
    if recorded_owner != "owner-42":
        print(f"FAIL: gate received owner {recorded_owner!r}, expected 'owner-42'")
        return False
    if not lexical.calls:
        print("FAIL: lexical gate was never consulted")
        return False
    if lexical.calls[0][1] != "owner-42":
        print(f"FAIL: lexical gate received owner {lexical.calls[0][1]!r}, expected 'owner-42'")
        return False
    return True


async def test_gate_reuses_query_embedding() -> bool:
    """The router reuses its embedding for retrieval in the service."""
    router, _, scorer, _ = build_semantic_router()
    scorer.scores = {"What is in my CV?": 0.45}
    retriever = RecordingRetriever()
    provider = RecordingProvider()
    service = build_service(retriever, provider, query_router=router)

    await service.chat("What is in my CV?", owner_id="owner-1")

    if not scorer.calls:
        print("FAIL: relevance gate was never consulted")
        return False
    gate_embedding = scorer.calls[0][2]
    if gate_embedding is None:
        print("FAIL: gate received no query embedding")
        return False
    if retriever.last_query_embedding != gate_embedding:
        print("FAIL: retrieval did not reuse the gate's query embedding")
        return False
    return True


async def test_gate_metadata_typos() -> bool:
    """Metadata typos resolve to METADATA without RAG or the LLM."""
    router, _, scorer, lexical = build_semantic_router()
    queries = [
        "which dcuments i upload in here?",
        "how many documnts do i have?",
        "did i uploadd the file?",
        "list my documnts please",
        "what uploads do i have?",
    ]
    for question in queries:
        actual = router.classify(question, owner_id="owner-1")
        if actual is not QueryCategory.METADATA:
            print(
                f"FAIL: metadata typo {question!r} -> {actual.value}, "
                f"expected {QueryCategory.METADATA.value}"
            )
            return False
        if scorer.calls or lexical.calls:
            print(
                f"FAIL: metadata typo {question!r} consulted the gates "
                f"(semantic={len(scorer.calls)}, lexical={len(lexical.calls)})"
            )
            return False
    return True


async def test_gate_metadata_typo_service_path() -> bool:
    """A metadata-typo query answers from the repository without retrieval/LLM."""
    repository = FakeDocumentRepository(
        [make_document("Anukul Chandra-CV.pdf", "owner-1")]
    )
    router, _, scorer, lexical = build_semantic_router()
    retriever = RecordingRetriever()
    provider = RecordingProvider()
    service = build_service(retriever, provider, repository, query_router=router)

    response = await service.chat("which dcuments i upload in here?", owner_id="owner-1")

    if retriever.calls != 0:
        print("FAIL: metadata-typo query triggered retrieval")
        return False
    if provider.prompts:
        print("FAIL: metadata-typo query called the LLM")
        return False
    if response.provider != "metadata":
        print(f"FAIL: expected provider 'metadata', got {response.provider!r}")
        return False
    return True


async def test_deterministic_rules_take_precedence() -> bool:
    """Metadata and explicit-filename queries never consult the gate."""
    router, embedding_service, scorer, lexical = build_semantic_router()

    cases = [
        "list my documents please",
        "summarize Anukul-chandra Cv.pdf",
        "What documents have I uploaded?",
        "which dcuments i upload in here?",
    ]
    for question in cases:
        embedding_service.calls = 0
        scorer.calls = []
        lexical.calls = []
        actual = router.classify(question, owner_id="owner-1")
        if actual is QueryCategory.GENERAL:
            print(f"FAIL: deterministic {question!r} unexpectedly GENERAL")
            return False
        if embedding_service.calls != 0:
            print(
                f"FAIL: deterministic {question!r} still embedded the query "
                f"({embedding_service.calls} calls)"
            )
            return False
        if scorer.calls or lexical.calls:
            print(
                f"FAIL: deterministic {question!r} still consulted the gate "
                f"(semantic={len(scorer.calls)}, lexical={len(lexical.calls)})"
            )
            return False
    return True


async def test_router_without_scorer_is_deterministic() -> bool:
    """Without an embedding service or scorers the router stays deterministic."""
    router = QueryRouter()
    cases = [
        ("which dcuments i upload in here?", QueryCategory.METADATA),
        ("Hello", QueryCategory.GENERAL),
        ("List my documents", QueryCategory.METADATA),
        ("What is in my CV?", QueryCategory.GENERAL),
        ("summarize my resume.pdf", QueryCategory.DOCUMENT),
    ]
    for question, expected in cases:
        actual = router.classify(question, owner_id="owner-1")
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
        ("GATE: implicit document questions -> RAG", test_gate_implicit_document_questions),
        ("GATE: self-attribute questions -> RAG", test_gate_self_attribute_questions),
        ("GATE: personal + lexical evidence -> RAG", test_gate_personal_with_lexical_evidence),
        ("GATE: paraphrase/typo -> RAG", test_gate_paraphrase_and_typo),
        ("GATE: document-noun + BM25 rescue", test_gate_document_noun_rescue),
        ("GATE: ML/AI topic questions stay GENERAL", test_gate_topic_questions_stay_general),
        ("GATE: unrelated general -> GENERAL", test_gate_unrelated_general),
        ("GATE: topic threshold boundary", test_gate_topic_threshold_boundary),
        ("GATE: personal floor boundary", test_gate_personal_floor_boundary),
        ("GATE: empty corpus -> GENERAL", test_gate_empty_corpus_is_general),
        ("GATE: owner scoping", test_gate_owner_scoping),
        ("GATE: reuses query embedding", test_gate_reuses_query_embedding),
        ("GATE: metadata typos -> METADATA", test_gate_metadata_typos),
        ("GATE: metadata typo service path", test_gate_metadata_typo_service_path),
        ("GATE: deterministic takes precedence", test_deterministic_rules_take_precedence),
        ("ROUTER: no scorer = deterministic", test_router_without_scorer_is_deterministic),
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