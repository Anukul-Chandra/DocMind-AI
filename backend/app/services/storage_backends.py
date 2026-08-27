"""Provider-independent storage abstractions for vector and document metadata.

These interfaces decouple the retrieval/document business logic from the
concrete persistence mechanism (currently FAISS + a JSON metadata file). The
goal is to allow a future, database-backed backend to be swapped in through
dependency injection without touching the callers.

Design rules:
- The abstraction MUST NOT mention filesystem paths. Persistence destinations are
  an implementation detail configured at construction time; callers trigger a
  flush with the path-free ``persist()`` method.
- Snapshots are returned as an opaque ``VectorSnapshot`` handle. Callers may
  store and later restore it (for transactional rollback) but must not inspect
  its internals.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from app.services.vectorstore.workspace import DEFAULT_WORKSPACE


class VectorSnapshot:
    """Opaque, backend-specific handle to a point-in-time vector index state.

    Used by the upload compensation logic to roll back an index to its previous
    state when a later step fails. Callers must treat ``payload`` as opaque.
    """

    __slots__ = ("payload",)

    def __init__(self, payload: object) -> None:
        self.payload = payload


class VectorBackend(ABC):
    """Storage-agnostic interface for dense vector indexing and search."""

    @abstractmethod
    def add_embeddings(self, embeddings: list[list[float]]) -> None:
        """Append embeddings to the index."""

    @abstractmethod
    def search(
        self, query_embedding: list[float], k: int = 5
    ) -> tuple[list[list[float]], list[list[int]]]:
        """Return ``(distances, indices)`` for the nearest neighbours of ``query_embedding``."""

    @abstractmethod
    def get_embedding(self, index: int) -> list[float]:
        """Return the stored embedding vector at ``index``."""

    @abstractmethod
    def snapshot_state(self) -> VectorSnapshot:
        """Capture an opaque, restorable snapshot of the current index state."""

    @abstractmethod
    def restore_state(self, state: VectorSnapshot) -> None:
        """Restore a previously captured snapshot (rolling back to that state)."""

    @abstractmethod
    def persist(self) -> None:
        """Flush any buffered state to the configured destination (no-op if none)."""


class MetadataBackend(ABC):
    """Storage-agnostic interface for per-chunk document metadata."""

    @abstractmethod
    def add_documents(
        self,
        texts: list[str],
        filename: str,
        workspace_id: str = DEFAULT_WORKSPACE,
        document_id: Optional[str] = None,
        owner_id: str = "",
    ) -> None:
        """Record chunk metadata for a document."""

    @abstractmethod
    def get_document(self, index: int) -> dict:
        """Return the metadata record stored at ``index``."""

    @abstractmethod
    def get_all_documents(self) -> list[dict]:
        """Return every stored metadata record."""

    @abstractmethod
    def snapshot_documents(self) -> list[dict]:
        """Capture a restorable copy of all metadata records."""

    @abstractmethod
    def restore_documents(self, records: list[dict]) -> None:
        """Replace all records with ``records`` (rolling back to that state)."""

    @abstractmethod
    def persist(self) -> None:
        """Flush any buffered state to the configured destination (no-op if none)."""
