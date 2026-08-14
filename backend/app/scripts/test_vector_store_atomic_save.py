"""Regression test for atomic/crash-safe FAISS index persistence.

Verifies that ``VectorStore.save`` never leaves the target ``index.faiss``
partially written:

    A. Normal save preserves the index content.
    B. A later save atomically replaces the previous index and leaves no
       temporary files behind.
    C. A failure during the write step or during the final replacement keeps
       the previous index intact, removes the temporary file, and raises.
    D. Saving to a path whose parent directory does not exist creates the
       directory and persists successfully.

The FAISS index contents and ordering are never modified; only the persistence
mechanism is exercised. All scenarios use isolated temporary paths, so the
real backend/storage/faiss/index.faiss is never touched.

Usage (from backend/):
    python -m app.scripts.test_vector_store_atomic_save

Exit status is non-zero if any check fails.
"""

import sys
import tempfile
from pathlib import Path
from unittest import mock

from app.services import vector_store as vector_store_module
from app.services.vector_store import VectorStore

DIMENSION = 8


def _store_with_vectors(count: int) -> VectorStore:
    """Create an in-memory FAISS store with ``count`` distinct vectors.

    Args:
        count: The number of vectors to add.

    Returns:
        A VectorStore with ``count`` vectors.
    """
    store = VectorStore(DIMENSION)
    store.add_embeddings([[float(i + 1)] * DIMENSION for i in range(count)])
    return store


def _tmp_files(directory: Path) -> list[Path]:
    """Return the atomic-save temporary files present in a directory.

    Args:
        directory: The directory to scan.

    Returns:
        A list of temporary files matching the save prefix/suffix.
    """
    return sorted(directory.glob(".*.tmp"))


def main() -> int:
    """Run the atomic FAISS save scenarios."""
    print("=" * 60)
    print("VectorStore Atomic Save Test")
    print("=" * 60)

    checks: dict[str, bool] = {"failed": False}

    def check(name: str, passed: bool, detail: str = "") -> None:
        status = "[OK]" if passed else "[FAIL]"
        print(f"{status} {name}" + (f" - {detail}" if detail else ""))
        if not passed:
            checks["failed"] = True

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)

        # A. Normal save preserves the index content.
        target_a = tmp / "faiss" / "index.faiss"
        store_a = _store_with_vectors(3)
        store_a.save(str(target_a))
        reloaded_a = VectorStore.load(str(target_a), DIMENSION)
        _, indices_a = reloaded_a.search([1.0] * DIMENSION, 1)
        check(
            "A. reloaded index preserves the vector count",
            reloaded_a.ntotal == 3,
            f"ntotal={reloaded_a.ntotal}",
        )
        check(
            "A. reloaded index preserves content (search)",
            indices_a[0][0] == 0,
            f"nearest={indices_a[0][0]}",
        )
        check(
            "A. no temporary files remain after a successful save",
            not _tmp_files(tmp / "faiss"),
        )

        # B. A later save atomically replaces the previous index.
        target_b = tmp / "index.faiss"
        store_b = _store_with_vectors(2)
        store_b.save(str(target_b))
        store_b = _store_with_vectors(5)
        store_b.save(str(target_b))
        reloaded_b = VectorStore.load(str(target_b), DIMENSION)
        check(
            "B. second save replaces the first index",
            reloaded_b.ntotal == 5,
            f"ntotal={reloaded_b.ntotal}",
        )
        check(
            "B. no temporary files remain after replacement",
            not _tmp_files(tmp),
        )

        # C. Failure during the write step keeps the old index intact.
        target_c = tmp / "failure" / "index.faiss"
        store_c = _store_with_vectors(2)
        store_c.save(str(target_c))
        store_c_bad = _store_with_vectors(3)
        with mock.patch.object(
            vector_store_module.faiss,
            "write_index",
            side_effect=RuntimeError("simulated write failure"),
        ):
            raised = False
            try:
                store_c_bad.save(str(target_c))
            except RuntimeError:
                raised = True
        check(
            "C. write failure propagates from save",
            raised,
        )
        reloaded_c = VectorStore.load(str(target_c), DIMENSION)
        check(
            "C. previous index remains intact after a failed write",
            reloaded_c.ntotal == 2,
            f"ntotal={reloaded_c.ntotal}",
        )
        check(
            "C. temporary file cleaned up after a failed write",
            not _tmp_files(tmp / "failure"),
        )

        # C. Failure during the final replacement keeps the old index intact.
        store_c_bad = _store_with_vectors(3)
        with mock.patch.object(
            vector_store_module.os,
            "replace",
            side_effect=RuntimeError("simulated replace failure"),
        ):
            raised = False
            try:
                store_c_bad.save(str(target_c))
            except RuntimeError:
                raised = True
        check(
            "C. replace failure propagates from save",
            raised,
        )
        reloaded_c = VectorStore.load(str(target_c), DIMENSION)
        check(
            "C. previous index not replaced by a partial file",
            reloaded_c.ntotal == 2,
            f"ntotal={reloaded_c.ntotal}",
        )
        check(
            "C. temporary file cleaned up after a failed replace",
            not _tmp_files(tmp / "failure"),
        )

        # D. Saving to a path whose parent directory does not exist.
        target_d = tmp / "deep" / "nested" / "dir" / "index.faiss"
        store_d = _store_with_vectors(1)
        store_d.save(str(target_d))
        reloaded_d = VectorStore.load(str(target_d), DIMENSION)
        check(
            "D. parent directory is created on save",
            target_d.parent.is_dir(),
        )
        check(
            "D. saved index loads from a newly created directory",
            reloaded_d.ntotal == 1,
            f"ntotal={reloaded_d.ntotal}",
        )

    print("\n" + "=" * 60)
    print("VectorStore Atomic Save Test " + ("PASSED" if not checks["failed"] else "FAILED"))
    print("=" * 60)
    return 1 if checks["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())