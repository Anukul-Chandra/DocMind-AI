"""Snapshot/restore foundation for safe upload failure compensation.

Before a document indexing attempt begins, the upload flow can capture the
state of the stores it is about to mutate and restore that state later if the
attempt fails. This module coordinates three independent pieces of state:

- the FAISS index (in-memory),
- the MetadataStore (in-memory records),
- the persisted metadata file (``metadata.json``).

The FAISS-to-metadata positional ordering is preserved exactly: snapshotting
deep-clones the FAISS index and copies the metadata records in order, and
restoring swaps both back to the captured state. No arbitrary vector deletion
or removal is used.

This is the detection/restoration foundation only. It never decides when to
restore; a future compensation step will call :func:`restore_upload_state`
after a failed indexing attempt. Nothing here modifies documents.json,
ownership, deletion flags, or the physical PDF files.
"""

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from app.services.storage_backends import MetadataBackend, VectorBackend, VectorSnapshot


@dataclass
class UploadStateSnapshot:
    """The pre-operation state of the stores a document index mutates.

    Attributes:
        faiss: The captured FAISS index state.
        metadata_records: The captured metadata records, in order.
        metadata_path: The metadata file path the snapshot covers, or None.
        metadata_file_existed: Whether the metadata file existed at capture.
        metadata_file_bytes: The exact bytes of the metadata file at capture,
            or None when the file did not exist.
    """

    faiss: VectorSnapshot
    metadata_records: list[dict] = field(default_factory=list)
    metadata_path: str | None = None
    metadata_file_existed: bool = False
    metadata_file_bytes: bytes | None = None


def capture_upload_state(
    vector_store: VectorBackend,
    metadata_store: MetadataBackend,
    metadata_path: str | None = None,
) -> UploadStateSnapshot:
    """Capture the pre-operation state of the stores to be mutated.

    Args:
        vector_store: The FAISS-backed vector store to snapshot.
        metadata_store: The metadata store to snapshot.
        metadata_path: Optional path to the persisted metadata file to
            snapshot; its exact bytes are captured when it exists.

    Returns:
        An UploadStateSnapshot preserving the current FAISS index, metadata
        records, and persisted metadata file state.
    """
    faiss_snapshot = vector_store.snapshot_state()
    metadata_records = metadata_store.snapshot_documents()

    metadata_file_existed = False
    metadata_file_bytes = None
    if metadata_path is not None:
        path = Path(metadata_path)
        metadata_file_existed = path.exists()
        if metadata_file_existed:
            metadata_file_bytes = path.read_bytes()

    return UploadStateSnapshot(
        faiss=faiss_snapshot,
        metadata_records=metadata_records,
        metadata_path=str(metadata_path) if metadata_path is not None else None,
        metadata_file_existed=metadata_file_existed,
        metadata_file_bytes=metadata_file_bytes,
    )


def restore_upload_state(
    snapshot: UploadStateSnapshot,
    vector_store: VectorBackend,
    metadata_store: MetadataBackend,
) -> None:
    """Restore the stores to the state captured in a snapshot.

    The FAISS index and the in-memory metadata records are swapped back to the
    captured state, and the persisted metadata file is restored byte-exactly
    (or removed when it did not exist at capture).

    Args:
        snapshot: The snapshot captured before the operation.
        vector_store: The vector store to restore.
        metadata_store: The metadata store to restore.
    """
    vector_store.restore_state(snapshot.faiss)
    metadata_store.restore_documents(snapshot.metadata_records)

    if snapshot.metadata_path is None:
        return
    path = Path(snapshot.metadata_path)
    if snapshot.metadata_file_existed and snapshot.metadata_file_bytes is not None:
        _atomic_write_bytes(path, snapshot.metadata_file_bytes)
    elif not snapshot.metadata_file_existed and path.exists():
        path.unlink()


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write raw bytes to a file atomically.

    The data is written to a unique temporary file in the same directory and
    moved over the target with :func:`os.replace`, mirroring the atomic
    persistence used by JsonFileStore. On failure the temporary file is
    removed and the existing target is left untouched.

    Args:
        path: The file path to write to.
        data: The exact bytes to persist.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
