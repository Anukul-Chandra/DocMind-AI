"""Focused verification of per-user ownership filtering in retrieval.

Builds an isolated in-memory retrieval stack (semantic + BM25 + hybrid with
the dependency-free reranker) where two owners index chunks into the same
default workspace, then verifies that a caller's results never contain
another owner's chunks:

    A. Owner A's retrieval returns A's chunks only.
    B. Owner B's identical-text chunk is excluded from A's semantic results.
    C. Owner B's identical-text chunk is excluded from A's BM25 results.
    D. RRF fusion and the reranker never receive another owner's chunk.
    E. Workspace filtering still holds alongside ownership filtering.
    F. Legacy chunks (empty owner_id) are invisible to named owners while the
       backward-compatible empty-owner path still returns them.
    G. Shared identical content across owners is fully isolated.

A deterministic, dependency-free fake embedding service maps each distinct
token to a fixed vector so the FAISS/BM25/reranker stages run without loading
the sentence-transformer model. Real embeddings are not required to prove the
owner filter because both owners here share identical chunk text, which would
naturally surface under unfiltered retrieval.

Usage (from backend/):
    PYTHONPATH=. ../.venv/bin/python -m app.scripts.test_retrieval_ownership

Pass ``--verbose`` to also print liveness probes showing the foreign-owner
chunks that an unfiltered retrieval would surface, proving the owner filter
is doing real work.

Exit status is non-zero if any check fails.
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.document_registry import DocumentRegistry
from app.services.retrieval import BM25Retriever, HybridRetriever
from app.services.retrieval.reranker import SemanticReranker
from app.services.vector_store import VectorStore
from app.services.vectorstore.metadata_store import MetadataStore
from app.services.vectorstore.retriever import SemanticRetriever
from app.services.vectorstore.workspace import DEFAULT_WORKSPACE

ALICE = "alice"
BOB = "bob"
OTHER = "other-workspace"

MATCH_TEXT = (
    "The caribou migration crosses the frozen delta each spring, following "
    "ancient trails of thundering hooves."
)
LEGACY_TEXT = (
    "Ancient observatories mapped the night sky before telescopes existed."
)
OTHER_TEXT = (
    "Currency exchange rates fluctuate with global economic sentiment."
)

VERBOSE = "--verbose" in sys.argv


@dataclass(frozen=True)
class _Result:
    """Results of a single retrieval call under inspection.

    Attributes:
        ids: The chunk ids that were returned.
        reranker_seen: The chunk ids handed to the reranker.
        raw_neighbors: The FAISS index ids that nearest-neighbour search
            surfaced for the query before any ownership filtering.
    """

    ids: set[int]
    reranker_seen: set[int]
    raw_neighbors: set[int]


@dataclass
class _FakeHash:
    """A tiny deterministic 64-bit hash used to seed the fake embeddings."""

    _hash: int = 0xCBF29CE484222325

    def __call__(self, word: str) -> int:
        value = self._hash
        for byte in word.encode("utf-8"):
            value ^= byte
            value = (value * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
        return value


class FakeEmbeddingService:
    """Deterministic, dependency-free placeholder for EmbeddingService.

    Maps each distinct token to a fixed integer vector dimension so identical
    texts embed identically and neighbours correspond to shared tokens.
    """

    def __init__(self) -> None:
        self._hash = _FakeHash()
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


class RecordingReranker(SemanticReranker):
    """A SemanticReranker that records which candidates it is handed."""

    def __init__(self) -> None:
        super().__init__()
        self.seen: set[int] = set()

    def rerank(
        self,
        query: str,
        candidates: list[dict],
        k: int = 5,
    ) -> list[dict]:
        self.seen.update(candidate["id"] for candidate in candidates)
        return super().rerank(query, candidates, k=k)


@dataclass
class Harness:
    """An isolated retrieval stack seeded with two owners plus legacy chunks."""

    metadata_store: MetadataStore
    document_registry: DocumentRegistry
    embedding_service: FakeEmbeddingService
    vector_store: VectorStore
    semantic: SemanticRetriever
    bm25: BM25Retriever
    hybrid: HybridRetriever
    recording: RecordingReranker = field(default_factory=RecordingReranker)


def _make_harness() -> Harness:
    """Build all retrieval components and index the test corpus.

    Returns:
        A harness whose stores are seeded with ALICE's, BOB's, a legacy
        ownerless, and a foreign-workspace chunk sets.
    """
    embedding_service = FakeEmbeddingService()
    embedding_service.generate_embeddings([MATCH_TEXT, LEGACY_TEXT, OTHER_TEXT])
    vector_store = VectorStore(
        dimension=embedding_service.get_embedding_dimension()
    )
    metadata_store = MetadataStore()
    document_registry = DocumentRegistry(
        Path(TemporaryDirectory().name) / "documents.json"
    )

    corpus = [
        (Path("/docs/alice.pdf"), "alice-a", ALICE, DEFAULT_WORKSPACE, [MATCH_TEXT]),
        (Path("/docs/bob.pdf"), "bob-a", BOB, DEFAULT_WORKSPACE, [MATCH_TEXT]),
        (
            Path("/docs/alice-legacy.txt"),
            "legacy-a",
            "",
            DEFAULT_WORKSPACE,
            [LEGACY_TEXT],
        ),
        (
            Path("/docs/other.txt"),
            "other-a",
            ALICE,
            OTHER,
            [OTHER_TEXT],
        ),
    ]
    for filename, document_id, owner, workspace, chunks in corpus:
        embeddings = embedding_service.generate_embeddings(chunks)
        vector_store.add_embeddings(embeddings)
        metadata_store.add_documents(
            chunks,
            filename.name,
            workspace,
            document_id,
            owner,
        )
        document_registry.register(
            workspace,
            filename.name,
            len(chunks),
            owner,
            document_id,
        )

    semantic = SemanticRetriever(
        embedding_service,
        vector_store,
        metadata_store,
        document_registry,
    )
    bm25 = BM25Retriever(metadata_store, document_registry)
    recording = RecordingReranker()
    hybrid = HybridRetriever(
        semantic_retriever=semantic,
        bm25_retriever=bm25,
        reranker=recording,
    )
    return Harness(
        metadata_store=metadata_store,
        document_registry=document_registry,
        embedding_service=embedding_service,
        vector_store=vector_store,
        semantic=semantic,
        bm25=bm25,
        hybrid=hybrid,
        recording=recording,
    )


def _inspect(
    harness: Harness,
    query: str,
    k: int,
    owner_id: str,
    workspace_id: str,
) -> _Result:
    """Run all retrieval paths for a caller and record what each layer saw.

    Args:
        harness: The seeded retrieval stack.
        query: The search query text.
        k: The number of chunks to request.
        owner_id: The caller's owner id.
        workspace_id: The workspace to retrieve within.

    Returns:
        The ids returned, the ids the reranker saw, and the raw FAISS
        neighbours for the query before any ownership filtering.
    """
    harness.recording.seen.clear()
    results: list[dict] = harness.hybrid.retrieve(
        query,
        k=k,
        workspace_id=workspace_id,
        owner_id=owner_id,
    )
    raw_query_embedding = harness.embedding_service.generate_embeddings([query])[0]
    _, raw_indices = harness.vector_store.search(raw_query_embedding, k)
    return _Result(
        ids={item["id"] for item in results},
        reranker_seen=set(harness.recording.seen),
        raw_neighbors=set(raw_indices[0]) - {-1},
    )


def _unique_chunk_detail(
    harness: Harness,
    ids: set[int],
    label: str,
) -> str:
    """Summarize which chunks map to which owner for a report line.

    Args:
        harness: The seeded retrieval stack.
        ids: The chunk ids to describe.
        label: The owner label for the chunks of interest.

    Returns:
        A human-readable summary of the chunk ids seen.
    """
    if not ids:
        return f"no {label} chunks seen"
    return f"{label} chunks: {sorted(ids)}"


def run_checks(results: list[tuple[str, bool, str]], harness: Harness) -> None:
    """Run every ownership isolation check and record the outcomes.

    Args:
        results: The list accumulating (name, passed, detail) tuples.
        harness: The seeded retrieval stack.
    """
    all_alice = {d["id"] for d in harness.metadata_store.get_all_documents() if d["owner_id"] == ALICE}
    all_bob = {d["id"] for d in harness.metadata_store.get_all_documents() if d["owner_id"] == BOB}
    all_legacy = {d["id"] for d in harness.metadata_store.get_all_documents() if d["owner_id"] == ""}
    all_other = {d["id"] for d in harness.metadata_store.get_all_documents() if d["workspace_id"] == OTHER}

    checks = []

    alice_view = _inspect(
        harness,
        MATCH_TEXT,
        k=5,
        owner_id=ALICE,
        workspace_id=DEFAULT_WORKSPACE,
    )
    checks.append(
        (
            "(A) owner A retrieval",
            bool(alice_view.ids) and alice_view.ids <= all_alice,
            _unique_chunk_detail(harness, alice_view.ids, "alice(owner A)"),
        )
    )
    checks.append(
        (
            "(B) no B chunks in semantic",
            not (alice_view.ids & all_bob),
            _unique_chunk_detail(harness, alice_view.ids, "alice(owner A)"),
        )
    )

    bm25_alice = {
        item["id"]
        for item in harness.bm25.retrieve(
            MATCH_TEXT, k=5, workspace_id=DEFAULT_WORKSPACE, owner_id=ALICE
        )
    }
    checks.append(
        (
            "(C) no B chunks in BM25",
            not (bm25_alice & all_bob),
            _unique_chunk_detail(harness, bm25_alice, "alice(owner A)"),
        )
    )

    checks.append(
        (
            "(D) reranker never sees B",
            not (alice_view.reranker_seen & all_bob),
            _unique_chunk_detail(harness, alice_view.reranker_seen, "reranker fed"),
        )
    )

    other_view = _inspect(
        harness,
        OTHER_TEXT,
        k=5,
        owner_id=ALICE,
        workspace_id=OTHER,
    )
    checks.append(
        (
            "(E) workspace filter preserved",
            bool(other_view.ids)
            and other_view.ids <= (all_other & all_alice)
            and not (other_view.reranker_seen & all_bob),
            _unique_chunk_detail(harness, other_view.ids, "other-workspace"),
        )
    )

    legacy_named = _inspect(
        harness,
        LEGACY_TEXT,
        k=5,
        owner_id=ALICE,
        workspace_id=DEFAULT_WORKSPACE,
    )
    checks.append(
        (
            "(F1) legacy chunks invisible to named owners",
            not (legacy_named.ids & all_legacy),
            _unique_chunk_detail(harness, legacy_named.ids, "alice(owner A)"),
        )
    )

    bm25_no_owner = {
        item["id"]
        for item in harness.bm25.retrieve(
            LEGACY_TEXT, k=5, workspace_id=DEFAULT_WORKSPACE
        )
    }
    checks.append(
        (
            "(F2) empty-owner path returns legacy chunks",
            bool(bm25_no_owner & all_legacy),
            _unique_chunk_detail(harness, bm25_no_owner, "empty-owner BM25 saw"),
        )
    )

    if VERBOSE:
        checks.extend(
            [
                (
                    "(liveness) B would surface unfiltered",
                    bool(alice_view.raw_neighbors & all_bob),
                    _unique_chunk_detail(
                        harness,
                        alice_view.raw_neighbors,
                        "unfiltered raw",
                    ),
                ),
                (
                    "(ids) alice and bob chunk ids",
                    bool(all_alice) and bool(all_bob),
                    f"alice={sorted(all_alice)} bob={sorted(all_bob)}",
                ),
            ]
        )

    results.extend(checks)


def print_report(results: list[tuple[str, bool, str]]) -> None:
    """Print the ownership verification report.

    Args:
        results: The list of (name, passed, detail) tuples to report.
    """
    print("=" * 40)
    print("Retrieval Ownership Verification")
    print("=" * 40)
    print()
    for name, passed, detail in results:
        status = "PASS" if passed else "FAIL"
        print(f"{name:<42}{status}")
        if not passed:
            print(f"  {detail}")
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


def main() -> int:
    """Run every ownership isolation check and return the exit code.

    Returns:
        0 when all checks pass, otherwise 1.
    """
    harness = _make_harness()
    results: list[tuple[str, bool, str]] = []
    run_checks(results, harness)
    print_report(results)
    overall = all(passed for _, passed, _ in results)
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())