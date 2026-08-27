"""Postgres/pgvector implementation of the ``VectorBackend`` abstraction.

This backend is intentionally dormant: it is NOT wired into
``app.api.dependencies`` and the application continues to use the FAISS +
JSON stack. It exists so a future step can select it (via the persistence
backend configuration) without touching the retrievers, ``DocumentService``,
CRAG, or any callers.

Semantics are kept identical to ``VectorStore`` (FAISS ``IndexFlatL2``):

- ``add_embeddings`` appends vectors in insertion order and assigns a gapless
  positional ``chunk_index`` (0-based) that lines up with the metadata record
  at the same position.
- ``search`` returns the nearest neighbours ordered by **squared L2 distance**,
  matching the distance FAISS ``IndexFlatL2`` reports. We compute squared L2 in
  SQL as ``l2_distance * l2_distance`` (the ``<->`` pgvector operator) because
  pgvector exposes ``l2_distance`` (plain L2), not a squared variant. The
  ordering is identical to FAISS; only the absolute scale differs, and (as with
  FAISS) the retriever recomputes its own similarity score from the raw vector
  via ``get_embedding``.
- ``snapshot_state`` / ``restore_state`` mirror the FAISS rollback used by the
  upload compensation logic: they capture/restore the append watermark so a
  failed indexing attempt can drop the vectors it added.

Ownership/workspace filtering: the ``search`` method accepts optional
``owner_id`` / ``workspace_id`` keyword arguments. When supplied they are
applied as SQL ``WHERE`` conditions (DB-level pushdown). When omitted, ``search``
behaves exactly like the FAISS backend (returns candidates; the retriever
applies ownership filtering against the metadata store). This keeps the
``VectorBackend`` interface unchanged while still allowing the safer
DB-level filter.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.models.vector_chunk import VectorChunk
from app.db.session import SessionFactory
from app.services.storage_backends import VectorBackend, VectorSnapshot
from pgvector.sqlalchemy import Vector


class PostgresVectorStore(VectorBackend):
    """Dense vector store backed by Postgres + pgvector."""

    def __init__(
        self, dimension: int, session_factory: Optional[SessionFactory] = None
    ) -> None:
        self._dimension = dimension
        self._session_factory = session_factory
        # Next positional chunk_index to assign. ``None`` means "not yet seeded
        # from the database"; it is lazily computed on first write.
        self._seq: Optional[int] = None

    # ------------------------------------------------------------------
    # Session handling
    # ------------------------------------------------------------------
    def _session(self) -> Session:
        if self._session_factory is None:
            raise RuntimeError(
                "PostgresVectorStore is not configured with a session factory"
            )
        return self._session_factory()

    def _next_index(self) -> int:
        if self._seq is None:
            with self._session() as session:
                max_index = session.execute(
                    select(func.max(VectorChunk.chunk_index))
                ).scalar()
            self._seq = (max_index + 1) if max_index is not None else 0
        return self._seq

    # ------------------------------------------------------------------
    # VectorBackend interface
    # ------------------------------------------------------------------
    def add_embeddings(self, embeddings: list[list[float]]) -> None:
        start = self._next_index()
        with self._session() as session:
            for offset, embedding in enumerate(embeddings):
                session.add(
                    VectorChunk(
                        chunk_index=start + offset,
                        embedding=embedding,
                        document_id="",
                        owner_id="",
                        workspace_id="",
                    )
                )
            session.commit()
        self._seq = start + len(embeddings)

    def search(
        self,
        query_embedding: list[float],
        k: int = 5,
        owner_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> tuple[list[list[float]], list[list[int]]]:
        # Squared L2 to match FAISS IndexFlatL2 (which returns squared L2).
        distance = VectorChunk.embedding.l2_distance(
            query_embedding
        ) * VectorChunk.embedding.l2_distance(query_embedding)
        stmt = (
            select(VectorChunk.chunk_index, distance.label("distance"))
            .order_by(distance)
            .limit(k)
        )
        if owner_id is not None:
            stmt = stmt.where(VectorChunk.owner_id == owner_id)
        if workspace_id is not None:
            stmt = stmt.where(VectorChunk.workspace_id == workspace_id)

        with self._session() as session:
            rows = session.execute(stmt).all()

        if not rows:
            return ([], [])

        indices = [[int(row.chunk_index) for row in rows]]
        distances = [[float(row.distance) for row in rows]]
        return (distances, indices)

    def get_embedding(self, index: int) -> list[float]:
        with self._session() as session:
            row = session.execute(
                select(VectorChunk.embedding).where(
                    VectorChunk.chunk_index == index
                )
            ).first()
        if row is None:
            raise IndexError("embedding index out of range")
        return list(row[0])

    def snapshot_state(self) -> VectorSnapshot:
        return VectorSnapshot({"watermark": self._seq if self._seq is not None else 0})

    def restore_state(self, state: VectorSnapshot) -> None:
        if not isinstance(state, VectorSnapshot):
            raise TypeError("restore_state expects a VectorSnapshot")
        watermark = state.payload["watermark"]
        with self._session() as session:
            session.execute(
                delete(VectorChunk).where(VectorChunk.chunk_index >= watermark)
            )
            session.commit()
        self._seq = watermark

    def persist(self) -> None:
        # Each write is committed immediately, so there is nothing to flush.
        return None

    # ------------------------------------------------------------------
    # Convenience (mirrors the FAISS VectorStore.ntotal helper)
    # ------------------------------------------------------------------
    @property
    def ntotal(self) -> int:
        if self._seq is not None:
            return self._seq
        with self._session() as session:
            return (
                session.execute(
                    select(func.count()).select_from(VectorChunk)
                ).scalar()
                or 0
            )
