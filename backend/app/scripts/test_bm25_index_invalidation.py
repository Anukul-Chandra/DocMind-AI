"""Focused regression verification that the BM25 index stays fresh.

Scenario (matches the reported bug): the BM25 index was built only once,
lazily, from the shared MetadataStore, so a document uploaded after the first
retrieval stayed invisible to keyword search until the backend restarted. This
script proves the fix:

    1. Index document A and confirm it is retrievable.
    2. Index document B only after the BM25 index has already been built by
       real retrieval calls.
    3. Query for terms unique to document B.
    4. Confirm document B is now retrievable, without any process restart,
       through both the standalone BM25 retriever and the full hybrid
       (FAISS + BM25 + RRF + reranker) flow.
    5. Confirm document A remains retrievable after the index is refreshed.

A deterministic, dependency-free fake embedding service maps each distinct
token to a fixed vector, so the semantic/FAISS stages run without loading the
sentence-transformer model. BM25 itself is pure text, so the keyword path is
verified independently of the embedding stage.

Usage (from backend/):
    python -m app.scripts.test_bm25_index_invalidation

Exit status is non-zero if any check fails.
"""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.document_registry import DocumentRegistry
from app.services.retrieval import BM25Retriever, HybridRetriever
from app.services.vector_store import VectorStore
from app.services.vectorstore.metadata_store import MetadataStore
from app.services.vectorstore.retriever import SemanticRetriever
from app.services.vectorstore.workspace import DEFAULT_WORKSPACE

OWNER = "regression-owner"

DOC_A_TEXT = (
    "The caribou migration crosses the frozen delta each spring, following "
    "ancient trails of thundering hooves."
)
DOC_B_TEXT = (
    "Geothermal turbines harness volcanic heat to generate basalt reservoirs "
    "beneath the arctic tundra."
)
DOC_A_QUERY = "caribou migration frozen delta"
DOC_B_QUERY = "geothermal volcanic turbines"

# Text and queries that may be embedded, pre-seeded so the fake embedding
# dimension is fixed before the VectorStore is constructed.
_SEED_TEXTS = [DOC_A_TEXT, DOC_B_TEXT, DOC_A_QUERY, DOC_B_QUERY]


class FakeEmbeddingService:
    """Deterministic, dependency-free placeholder for EmbeddingService.

    Maps each distinct token to a fixed vector dimension so identical texts
    embed identically and neighbours correspond to shared tokens.
    """

    def __init__(self) -> None:
        self._word_ids: dict[str, int] = {}

    def _vector(self, text: str) -> list[int]:
        words = text.lower().split()
        indexed: list[int] = []
        for word in words:
            word_id = self._word_ids.get(word)
            if word_id is None:
                word_id = len(self._word_ids)
                self._word_ids[word] = word_id
            indexed.append(word_id)
        vector = [0] * len(self._word_ids)
        for word_id in indexed:
            vector[word_id] += 1
        return vector

    def generate_embeddings(self, texts: list[str]) -> list[list[int]]:
        return [self._vector(text) for text in texts]

    def get_embedding_dimension(self) -> int:
        return len(self._word_ids)


def _index_document(
    text: str,
    filename: str,
    document_id: str,
    embedding_service: FakeEmbeddingService,
    vector_store: VectorStore,
    metadata_store: MetadataStore,
    registry: DocumentRegistry,
) -> None:
    """Run the same storage steps DocumentService.index_document performs."""
    embeddings = embedding_service.generate_embeddings([text])
    vector_store.add_embeddings(embeddings)
    metadata_store.add_documents(
        [text],
        filename,
        DEFAULT_WORKSPACE,
        document_id,
        OWNER,
    )
    registry.register(
        DEFAULT_WORKSPACE,
        filename,
        1,
        OWNER,
        document_id,
    )


def run_checks() -> list[tuple[str, bool, str]]:
    """Run the staleness regression checks and return (name, passed, detail)."""
    with TemporaryDirectory() as temp_dir:
        embedding_service = FakeEmbeddingService()
        embedding_service.generate_embeddings(_SEED_TEXTS)
        vector_store = VectorStore(
            dimension=embedding_service.get_embedding_dimension()
        )
        metadata_store = MetadataStore()
        registry = DocumentRegistry(Path(temp_dir) / "documents.json")

        # Step 1: index document A.
        _index_document(
            DOC_A_TEXT,
            "caribou.pdf",
            "doc-a",
            embedding_service,
            vector_store,
            metadata_store,
            registry,
        )

        semantic = SemanticRetriever(
            embedding_service,
            vector_store,
            metadata_store,
            registry,
        )
        bm25 = BM25Retriever(metadata_store, registry)
        hybrid = HybridRetriever(
            semantic_retriever=semantic,
            bm25_retriever=bm25,
        )

        checks: list[tuple[str, bool, str]] = []

        # Step 2: confirm A is retrievable, which also builds the BM25 index.
        bm25_a = {
            item["id"]
            for item in bm25.retrieve(
                DOC_A_QUERY, k=5, workspace_id=DEFAULT_WORKSPACE, owner_id=OWNER
            )
        }
        checks.append(
            (
                "(1) initial doc A retrievable via BM25",
                1 in bm25_a,
                f"bm25 ids: {sorted(bm25_a)}",
            )
        )

        hybrid_a = {
            item["id"]
            for item in hybrid.retrieve(
                DOC_A_QUERY, k=5, workspace_id=DEFAULT_WORKSPACE, owner_id=OWNER
            )
        }
        checks.append(
            (
                "(2) initial doc A retrievable via hybrid",
                1 in hybrid_a,
                f"hybrid ids: {sorted(hybrid_a)}",
            )
        )

        # The BM25 index has now been built once, from doc A alone.
        index_before = len(bm25._doc_tokens)  # type: ignore[attr-defined]
        checks.append(
            (
                "(3) BM25 index initialized with only doc A",
                index_before == 1,
                f"indexed chunks before second upload: {index_before}",
            )
        )

        # Step 3: add document B after the BM25 index is already initialized.
        _index_document(
            DOC_B_TEXT,
            "geothermal.pdf",
            "doc-b",
            embedding_service,
            vector_store,
            metadata_store,
            registry,
        )

        # Step 4: query for content unique to B, without any restart.
        bm25_b = {
            item["id"]
            for item in bm25.retrieve(
                DOC_B_QUERY, k=5, workspace_id=DEFAULT_WORKSPACE, owner_id=OWNER
            )
        }
        checks.append(
            (
                "(4) post-upload doc B retrievable via BM25 without restart",
                2 in bm25_b,
                f"bm25 ids: {sorted(bm25_b)}",
            )
        )

        hybrid_b = {
            item["id"]
            for item in hybrid.retrieve(
                DOC_B_QUERY, k=5, workspace_id=DEFAULT_WORKSPACE, owner_id=OWNER
            )
        }
        checks.append(
            (
                "(5) post-upload doc B retrievable via hybrid without restart",
                2 in hybrid_b,
                f"hybrid ids: {sorted(hybrid_b)}",
            )
        )

        # The BM25 index must now cover the whole stored corpus.
        corpus_size = len(metadata_store.get_all_documents())
        index_after = len(bm25._doc_tokens)  # type: ignore[attr-defined]
        checks.append(
            (
                "(6) BM25 index covers the updated corpus",
                index_after == corpus_size == 2,
                f"indexed chunks: {index_after}, stored chunks: {corpus_size}",
            )
        )

        # Step 5: doc A must still be retrievable after the index refresh.
        bm25_a_again = {
            item["id"]
            for item in bm25.retrieve(
                DOC_A_QUERY, k=5, workspace_id=DEFAULT_WORKSPACE, owner_id=OWNER
            )
        }
        checks.append(
            (
                "(7) doc A remains retrievable after refresh",
                1 in bm25_a_again,
                f"bm25 ids: {sorted(bm25_a_again)}",
            )
        )

        return checks


def print_report(results: list[tuple[str, bool, str]]) -> None:
    """Print the regression verification report."""
    print("=" * 40)
    print("BM25 Index Invalidation Verification")
    print("=" * 40)
    print()
    for name, passed, detail in results:
        status = "PASS" if passed else "FAIL"
        print(f"{name:<48}{status}")
        if not passed:
            print(f"  {detail}")
    print()
    print("=" * 40)
    print()
    overall = all(passed for _, passed, _ in results)
    print("PASS" if overall else "FAIL")
    print()
    print("=" * 40)
    print()


def main() -> int:
    """Run every staleness check and return the exit code.

    Returns:
        0 when all checks pass, otherwise 1.
    """
    results = run_checks()
    print_report(results)
    overall = all(passed for _, passed, _ in results)
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())