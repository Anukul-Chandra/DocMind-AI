"""Regression test for the upload-state snapshot/restore foundation.

Exercises ``app.services.document.state_snapshot`` and the snapshot/restore
primitives it builds on (VectorStore index clone, MetadataStore record copy,
byte-exact metadata file restore):

    A. A captured FAISS index can be restored exactly.
    B. Captured metadata records can be restored exactly.
    C. FAISS and metadata can both be changed and then restored together.
    D. Ordering is unchanged after restore (FAISS positions and metadata ids).
    E. Pre-existing data remains intact after a mutate/restore cycle.
    F. The persisted metadata file is restored byte-exactly, including the
       case where it did not exist before the operation.
    G. All scenarios run on temporary isolated paths; the real
       backend/storage files are never modified.

Usage (from backend/):
    python -m app.scripts.test_upload_state_snapshot

Exit status is non-zero if any check fails.
"""

import sys
import tempfile
from pathlib import Path

from app.core.config import settings
from app.services.document.state_snapshot import (
    capture_upload_state,
    restore_upload_state,
)
from app.services.vector_store import VectorStore
from app.services.vectorstore.metadata_store import MetadataStore
from app.services.vectorstore.workspace import DEFAULT_WORKSPACE

DIMENSION = 8


def _store_with_vectors(count: int) -> VectorStore:
    """Create a vector store with ``count`` distinct vectors.

    Args:
        count: The number of vectors to add.

    Returns:
        A VectorStore whose vector ``i`` is a constant ``i + 1`` vector.
    """
    store = VectorStore(DIMENSION)
    if count:
        store.add_embeddings([[float(i + 1)] * DIMENSION for i in range(count)])
    return store


def _make_metadata(entries: list[tuple[str, str, str, str]]) -> MetadataStore:
    """Create a metadata store from ``(document_id, filename, owner, text)``.

    Args:
        entries: The chunk entries to add, in order.

    Returns:
        A MetadataStore holding one chunk per entry, ids sequential from 1.
    """
    store = MetadataStore()
    for document_id, filename, owner_id, text in entries:
        store.add_documents(
            [text], filename, DEFAULT_WORKSPACE, document_id, owner_id
        )
    return store


def _nearest(vector_store: VectorStore, value: float) -> int:
    """Return the index of the nearest vector for a constant-vector query.

    Args:
        vector_store: The store to search.
        value: The constant value filling every dimension of the query.

    Returns:
        The index of the nearest neighbour.
    """
    _, indices = vector_store.search([value] * DIMENSION, 1)
    return indices[0][0]


def _record_summary(records: list[dict]) -> list[tuple]:
    """Return an order-sensitive summary of metadata records.

    Args:
        records: The metadata records to summarize.

    Returns:
        A list of ``(id, document_id, filename, owner_id, text)`` tuples.
    """
    return [
        (
            record["id"],
            record["document_id"],
            record["filename"],
            record["owner_id"],
            record["text"],
        )
        for record in records
    ]


def main() -> int:
    """Run the snapshot/restore scenarios."""
    print("=" * 60)
    print("Upload State Snapshot/Restore Test")
    print("=" * 60)

    checks: dict[str, bool] = {"failed": False}

    def check(name: str, passed: bool, detail: str = "") -> None:
        status = "[OK]" if passed else "[FAIL]"
        print(f"{status} {name}" + (f" - {detail}" if detail else ""))
        if not passed:
            checks["failed"] = True

    real_metadata_before = Path(settings.metadata_path).read_bytes()
    real_faiss_before = Path(settings.faiss_index_path).read_bytes()

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)

        # A. Captured FAISS index restored exactly.
        vector_store = _store_with_vectors(2)
        metadata_store = MetadataStore()
        snapshot_a = capture_upload_state(vector_store, metadata_store)
        vector_store.add_embeddings([[9.0] * DIMENSION])
        check(
            "A. index mutated after capture",
            vector_store.ntotal == 3,
            f"ntotal={vector_store.ntotal}",
        )
        restore_upload_state(snapshot_a, vector_store, metadata_store)
        check(
            "A. FAISS restored to the captured count",
            vector_store.ntotal == 2,
            f"ntotal={vector_store.ntotal}",
        )
        check(
            "A. FAISS content preserved after restore",
            _nearest(vector_store, 1.0) == 0 and _nearest(vector_store, 2.0) == 1,
        )

        # B. Captured metadata restored exactly.
        vector_store = _store_with_vectors(0)
        metadata_store = _make_metadata(
            [("doc-1", "a.pdf", "alice", "chunk A"), ("doc-2", "b.pdf", "bob", "chunk B")]
        )
        snapshot_b = capture_upload_state(vector_store, metadata_store)
        metadata_store.add_documents(
            ["chunk C"], "c.pdf", DEFAULT_WORKSPACE, "doc-3", "carol"
        )
        restore_upload_state(snapshot_b, vector_store, metadata_store)
        restored = metadata_store.get_all_documents()
        check(
            "B. metadata restored to the captured count",
            len(restored) == 2,
            f"count={len(restored)}",
        )
        check(
            "B. metadata fields preserved after restore",
            _record_summary(restored)
            == [
                (1, "doc-1", "a.pdf", "alice", "chunk A"),
                (2, "doc-2", "b.pdf", "bob", "chunk B"),
            ],
            str(_record_summary(restored)),
        )

        # C. FAISS and metadata both changed, then restored together.
        vector_store = _store_with_vectors(2)
        metadata_store = _make_metadata(
            [("doc-1", "a.pdf", "alice", "chunk A"), ("doc-2", "b.pdf", "bob", "chunk B")]
        )
        snapshot_c = capture_upload_state(vector_store, metadata_store)
        vector_store.add_embeddings([[9.0] * DIMENSION, [10.0] * DIMENSION])
        metadata_store.add_documents(
            ["chunk C", "chunk D"], "c.pdf", DEFAULT_WORKSPACE, "doc-3", "carol"
        )
        restore_upload_state(snapshot_c, vector_store, metadata_store)
        check(
            "C. both stores restored to the captured state",
            vector_store.ntotal == 2 and len(metadata_store.get_all_documents()) == 2,
            f"faiss={vector_store.ntotal} metadata={len(metadata_store.get_all_documents())}",
        )

        # D. Ordering unchanged after restore.
        restored = metadata_store.get_all_documents()
        check(
            "D. metadata ids remain sequential after restore",
            [record["id"] for record in restored] == [1, 2],
            str([record["id"] for record in restored]),
        )
        check(
            "D. FAISS vector ordering preserved after restore",
            _nearest(vector_store, 1.0) == 0
            and _nearest(vector_store, 2.0) == 1
            and _nearest(vector_store, 9.0) in (0, 1),
            f"n1={_nearest(vector_store, 1.0)} n2={_nearest(vector_store, 2.0)}",
        )

        # E. Pre-existing data remains intact after a mutate/restore cycle.
        vector_store = _store_with_vectors(3)
        metadata_store = _make_metadata(
            [
                ("doc-pre1", "pre1.pdf", "alice", "pre A"),
                ("doc-pre1", "pre1.pdf", "alice", "pre B"),
                ("doc-pre2", "pre2.pdf", "bob", "pre C"),
            ]
        )
        before = _record_summary(metadata_store.get_all_documents())
        snapshot_e = capture_upload_state(vector_store, metadata_store)
        vector_store.add_embeddings([[5.0] * DIMENSION, [6.0] * DIMENSION])
        metadata_store.add_documents(
            ["new chunk"], "new.pdf", DEFAULT_WORKSPACE, "doc-new", "dave"
        )
        restore_upload_state(snapshot_e, vector_store, metadata_store)
        check(
            "E. pre-existing data intact after restore",
            vector_store.ntotal == 3
            and _record_summary(metadata_store.get_all_documents()) == before,
            f"faiss={vector_store.ntotal}",
        )

        # F. Persisted metadata file restored byte-exactly.
        metadata_path = tmp / "metadata.json"
        vector_store = _store_with_vectors(1)
        metadata_store = _make_metadata([("doc-1", "a.pdf", "alice", "chunk A")])
        metadata_store.save(str(metadata_path))
        snapshot_f = capture_upload_state(vector_store, metadata_store, str(metadata_path))
        metadata_store.add_documents(
            ["chunk B"], "b.pdf", DEFAULT_WORKSPACE, "doc-2", "bob"
        )
        metadata_store.save(str(metadata_path))
        check(
            "F. metadata file mutated before restore",
            metadata_path.read_bytes() != snapshot_f.metadata_file_bytes,
        )
        restore_upload_state(snapshot_f, vector_store, metadata_store)
        check(
            "F. persisted metadata file restored byte-exactly",
            metadata_path.read_bytes() == snapshot_f.metadata_file_bytes,
        )
        check(
            "F. in-memory metadata restored alongside the file",
            len(metadata_store.get_all_documents()) == 1,
            f"count={len(metadata_store.get_all_documents())}",
        )

        # F. Persisted state restored when the file did not exist before.
        missing_path = tmp / "empty_dir" / "metadata.json"
        vector_store = _store_with_vectors(1)
        metadata_store = MetadataStore()
        snapshot_f2 = capture_upload_state(
            vector_store, metadata_store, str(missing_path)
        )
        check(
            "F. capture records a missing metadata file",
            not snapshot_f2.metadata_file_existed,
        )
        metadata_store.add_documents(
            ["chunk X"], "x.pdf", DEFAULT_WORKSPACE, "doc-x", "eve"
        )
        metadata_store.save(str(missing_path))
        check(
            "F. metadata file created during the operation",
            missing_path.exists(),
        )
        restore_upload_state(snapshot_f2, vector_store, metadata_store)
        check(
            "F. metadata file removed when it did not exist before",
            not missing_path.exists(),
        )
        check(
            "F. in-memory metadata emptied alongside the file",
            len(metadata_store.get_all_documents()) == 0,
        )

    # G. Real backend/storage files untouched.
    real_metadata_after = Path(settings.metadata_path).read_bytes()
    real_faiss_after = Path(settings.faiss_index_path).read_bytes()
    check(
        "G. real metadata.json untouched",
        real_metadata_before == real_metadata_after,
    )
    check(
        "G. real index.faiss untouched",
        real_faiss_before == real_faiss_after,
    )

    print("\n" + "=" * 60)
    print("Upload State Snapshot/Restore Test " + ("PASSED" if not checks["failed"] else "FAILED"))
    print("=" * 60)
    return 1 if checks["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())