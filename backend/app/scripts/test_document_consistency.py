"""Manual test for the document storage consistency checker.

Exercises ``app.services.document.consistency.check_consistency`` against an
isolated temporary dataset:

    A. Matching FAISS + metadata -> healthy.
    B. FAISS count mismatch -> unhealthy.
    C. Metadata referencing an unknown document -> orphan detected.
    D. Legacy ownerless metadata (empty document id) -> detected.
    E. Metadata of a soft-deleted document -> detected (and does not make the
       report unhealthy, matching the documented soft-delete semantics).
    F. Registry chunk_count mismatch -> detected.
    G. Clean dataset -> no false positives.
    H. JSON registry through the DocumentRepository abstraction works
       correctly, and the checker never mutates the registry file.

The checker is read-only: every scenario runs on temporary paths and no real
backend/storage data is touched.

Usage (from backend/):
    python -m app.scripts.test_document_consistency

Exit status is non-zero if any check fails.
"""

import sys
import tempfile
from pathlib import Path

from app.repositories.json.document_repository import JsonDocumentRepository
from app.services.document.consistency import check_consistency
from app.services.document_registry import DocumentRegistry
from app.services.vector_store import VectorStore
from app.services.vectorstore.metadata_store import MetadataStore

DIMENSION = 8
DEFAULT_WORKSPACE = "default"


def _make_vector_store(vectors: int = 0) -> VectorStore:
    """Create an in-memory FAISS store with ``vectors`` zero-ish vectors.

    Args:
        vectors: The number of vectors to pre-add.

    Returns:
        A VectorStore with the requested number of vectors.
    """
    store = VectorStore(DIMENSION)
    if vectors:
        store.add_embeddings([[0.1 * (i + 1)] * DIMENSION for i in range(vectors)])
    return store


def _make_registry(tmp: Path) -> tuple[DocumentRegistry, JsonDocumentRepository]:
    """Create an isolated JSON document registry and its repository.

    Args:
        tmp: The temporary directory owning the registry file.

    Returns:
        A tuple of the registry and the repository abstraction over it.
    """
    registry = DocumentRegistry(tmp / "documents.json")
    return registry, JsonDocumentRepository(registry)


def _add_chunks(
    vector_store: VectorStore,
    metadata_store: MetadataStore,
    texts: list[str],
    filename: str,
    document_id: str | None,
    owner_id: str,
    workspace_id: str = DEFAULT_WORKSPACE,
    vector_count: int | None = None,
) -> None:
    """Add vectors and metadata chunks for a set of texts.

    Args:
        vector_store: The vector store to add vectors to.
        metadata_store: The metadata store to add chunks to.
        texts: The chunk texts.
        filename: The display filename.
        document_id: The owning document id (None for legacy ownerless chunks).
        owner_id: The chunk owner (empty for legacy ownerless chunks).
        workspace_id: The workspace the chunks belong to.
        vector_count: The number of vectors to add; defaults to one vector per
            text (the normal aligned case). Pass a smaller number to build a
            mismatched dataset.
    """
    if vector_count is None:
        vector_count = len(texts)
    vector_store.add_embeddings([[0.5] * DIMENSION for _ in range(vector_count)])
    metadata_store.add_documents(
        texts,
        filename,
        workspace_id,
        document_id,
        owner_id,
    )


def main() -> int:
    """Run the consistency checker scenarios."""
    print("=" * 60)
    print("Document Storage Consistency Checker Test")
    print("=" * 60)

    checks: dict[str, bool] = {"failed": False}

    def check(name: str, passed: bool, detail: str = "") -> None:
        status = "[OK]" if passed else "[FAIL]"
        print(f"{status} {name}" + (f" - {detail}" if detail else ""))
        if not passed:
            checks["failed"] = True

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)

        # A. Matching FAISS + metadata -> healthy.
        registry_a, repo_a = _make_registry(tmp / "a")
        registry_a.register(
            DEFAULT_WORKSPACE, "a.pdf", 1, "alice", document_id="doc-a"
        )
        vector_store = _make_vector_store()
        metadata_store = MetadataStore()
        _add_chunks(
            vector_store, metadata_store, ["chunk A"], "a.pdf", "doc-a", "alice"
        )
        report = check_consistency(vector_store, metadata_store, repo_a)
        check(
            "A. matching counts are reported healthy",
            report.vector_metadata_match
            and report.vector_count == 1
            and report.metadata_count == 1
            and report.healthy,
            f"vectors={report.vector_count} metadata={report.metadata_count}",
        )
        check(
            "A. no divergences on a matching dataset",
            not report.unmatched_vector_indices
            and not report.metadata_without_vector_ids
            and not report.orphan_metadata
            and not report.legacy_ownerless_chunks
            and not report.deleted_document_chunks
            and not report.registry_chunk_count_mismatches,
        )

        # B. FAISS count mismatch -> unhealthy.
        registry_b, repo_b = _make_registry(tmp / "b")
        registry_b.register(
            DEFAULT_WORKSPACE, "b.pdf", 2, "alice", document_id="doc-b"
        )
        vector_store = _make_vector_store()
        metadata_store = MetadataStore()
        _add_chunks(
            vector_store,
            metadata_store,
            ["chunk B1", "chunk B2"],
            "b.pdf",
            "doc-b",
            "alice",
            vector_count=1,
        )
        report = check_consistency(vector_store, metadata_store, repo_b)
        check(
            "B. FAISS/metadata count mismatch detected",
            report.vector_count == 1
            and report.metadata_count == 2
            and not report.vector_metadata_match
            and not report.healthy,
            f"vectors={report.vector_count} metadata={report.metadata_count}",
        )
        check(
            "B. metadata without a FAISS vector reported",
            report.metadata_without_vector_ids == [2],
            str(report.metadata_without_vector_ids),
        )

        # C. Metadata referencing an unknown document -> orphan detected.
        registry_c, repo_c = _make_registry(tmp / "c")
        registry_c.register(
            DEFAULT_WORKSPACE, "c.pdf", 0, "alice", document_id="doc-c"
        )
        vector_store = _make_vector_store(vectors=1)
        metadata_store = MetadataStore()
        _add_chunks(
            vector_store, metadata_store, ["ghost chunk"], "ghost.pdf", "doc-ghost", "alice"
        )
        report = check_consistency(vector_store, metadata_store, repo_c)
        check(
            "C. unknown document referenced -> orphan detected",
            len(report.orphan_metadata) == 1
            and report.orphan_metadata[0].document_id == "doc-ghost"
            and report.orphan_metadata[0].owner_id == "alice"
            and not report.healthy,
            str([r.document_id for r in report.orphan_metadata]),
        )

        # D. Legacy ownerless metadata -> detected, not a health failure.
        vector_store = _make_vector_store()
        metadata_store = MetadataStore()
        _add_chunks(
            vector_store, metadata_store, ["legacy chunk"], "legacy.pdf", None, ""
        )
        report = check_consistency(vector_store, metadata_store, repo_c)
        check(
            "D. legacy ownerless chunks reported separately",
            len(report.legacy_ownerless_chunks) == 1
            and report.legacy_ownerless_chunks[0].document_id == "",
            str([r.metadata_id for r in report.legacy_ownerless_chunks]),
        )
        check(
            "D. legacy chunks do not make the report unhealthy",
            report.healthy,
        )

        # E. Metadata of a soft-deleted document -> detected.
        registry_e, repo_e = _make_registry(tmp / "e")
        registry_e.register(
            DEFAULT_WORKSPACE, "e.pdf", 1, "alice", document_id="doc-e"
        )
        registry_e.delete_document("doc-e", "alice")
        vector_store = _make_vector_store()
        metadata_store = MetadataStore()
        _add_chunks(
            vector_store, metadata_store, ["deleted chunk"], "e.pdf", "doc-e", "alice"
        )
        report = check_consistency(vector_store, metadata_store, repo_e)
        check(
            "E. chunks of a deleted document detected",
            len(report.deleted_document_chunks) == 1
            and report.deleted_document_chunks[0].document_id == "doc-e",
            str([r.document_id for r in report.deleted_document_chunks]),
        )
        check(
            "E. deleted chunks do not make the report unhealthy",
            report.healthy,
        )

        # F. Registry chunk_count mismatch -> detected.
        registry_f, repo_f = _make_registry(tmp / "f")
        registry_f.register(
            DEFAULT_WORKSPACE, "f.pdf", 3, "alice", document_id="doc-f"
        )
        vector_store = _make_vector_store()
        metadata_store = MetadataStore()
        _add_chunks(
            vector_store, metadata_store, ["chunk F1"], "f.pdf", "doc-f", "alice"
        )
        report = check_consistency(vector_store, metadata_store, repo_f)
        check(
            "F. registry chunk_count mismatch detected",
            len(report.registry_chunk_count_mismatches) == 1
            and report.registry_chunk_count_mismatches[0].document_id == "doc-f"
            and report.registry_chunk_count_mismatches[0].registry_chunk_count == 3
            and report.registry_chunk_count_mismatches[0].metadata_chunk_count == 1
            and not report.healthy,
            str(
                [
                    f"{m.document_id}:{m.registry_chunk_count}!={m.metadata_chunk_count}"
                    for m in report.registry_chunk_count_mismatches
                ]
            ),
        )

        # G. Clean dataset -> no false positives.
        registry_g, repo_g = _make_registry(tmp / "g")
        registry_g.register(
            DEFAULT_WORKSPACE, "g1.pdf", 2, "alice", document_id="doc-g1"
        )
        registry_g.register(
            DEFAULT_WORKSPACE, "g2.pdf", 1, "bob", document_id="doc-g2"
        )
        vector_store = _make_vector_store()
        metadata_store = MetadataStore()
        _add_chunks(
            vector_store, metadata_store, ["G1a", "G1b"], "g1.pdf", "doc-g1", "alice"
        )
        _add_chunks(
            vector_store, metadata_store, ["G2"], "g2.pdf", "doc-g2", "bob"
        )
        report = check_consistency(vector_store, metadata_store, repo_g)
        check(
            "G. clean dataset reports no divergences",
            report.vector_count == 3
            and report.metadata_count == 3
            and report.vector_metadata_match
            and not report.orphan_metadata
            and not report.legacy_ownerless_chunks
            and not report.deleted_document_chunks
            and not report.registry_chunk_count_mismatches
            and not report.unmatched_vector_indices
            and not report.metadata_without_vector_ids
            and report.healthy,
            f"healthy={report.healthy}",
        )

        # H. JSON registry through the DocumentRepository abstraction, read-only.
        registry_h = tmp / "h"
        registry_h.mkdir()
        registry, repo_h = _make_registry(registry_h)
        registry.register(
            DEFAULT_WORKSPACE, "h1.pdf", 1, "alice", document_id="doc-h1"
        )
        registry.register(
            DEFAULT_WORKSPACE, "h2.pdf", 1, "bob", document_id="doc-h2"
        )
        vector_store = _make_vector_store()
        metadata_store = MetadataStore()
        _add_chunks(
            vector_store, metadata_store, ["H1"], "h1.pdf", "doc-h1", "alice"
        )
        _add_chunks(
            vector_store, metadata_store, ["H2"], "h2.pdf", "doc-h2", "bob"
        )
        registry_file = registry_h / "documents.json"
        before = registry_file.read_bytes()
        report = check_consistency(vector_store, metadata_store, repo_h)
        after = registry_file.read_bytes()
        check(
            "H. repository abstraction enumerates the full registry",
            len(repo_h.list_all_documents()) == 2,
            f"documents={len(repo_h.list_all_documents())}",
        )
        check(
            "H. checker works through the repository abstraction",
            report.healthy
            and report.vector_count == 2
            and report.metadata_count == 2
            and not report.orphan_metadata,
            f"healthy={report.healthy}",
        )
        check(
            "H. registry file unchanged by the check (read-only)",
            before == after,
        )

    print("\n" + "=" * 60)
    print("Consistency Checker Test " + ("PASSED" if not checks["failed"] else "FAILED"))
    print("=" * 60)
    return 1 if checks["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
