"""Postgres implementation of the ``MetadataBackend`` abstraction.

This backend is intentionally dormant: it is NOT wired into
``app.api.dependencies`` and the application continues to use the FAISS +
JSON stack. It exists so a future step can select it (via the persistence
backend configuration) without touching the retrievers, ``DocumentService``,
CRAG, or any callers.

It stores the same logical metadata as ``MetadataStore`` (JSON), keyed by a
gapless 0-based ``chunk_index`` that lines up with ``vector_chunks.chunk_index``
in the companion vector backend. The JSON ``id`` is derived as
``chunk_index + 1`` for drop-in compatibility.

Ownership/workspace filtering is preserved exactly as in the JSON backend: the
retriever applies ``is_eligible`` against the returned records (which carry
``owner_id`` / ``workspace_id`` / ``document_id``). To allow a safer DB-level
pushdown later, ``get_all_documents`` accepts optional ``owner_id`` /
``workspace_id`` keyword arguments that add SQL ``WHERE`` conditions when
supplied; omitting them reproduces the JSON backend's "return everything"
behavior.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.models.chunk_metadata import ChunkMetadata
from app.db.session import SessionFactory
from app.services.storage_backends import MetadataBackend
from app.services.vectorstore.workspace import DEFAULT_WORKSPACE


class PostgresMetadataStore(MetadataBackend):
    """Document chunk metadata backed by Postgres."""

    def __init__(
        self,
        path: Optional[str] = None,
        session_factory: Optional[SessionFactory] = None,
    ) -> None:
        # ``path`` is accepted only for signature compatibility with the JSON
        # MetadataStore and is ignored by this backend.
        self._path = path
        self._session_factory = session_factory
        # Next positional chunk_index to assign (lazy-seeded from the DB).
        self._seq: Optional[int] = None

    # ------------------------------------------------------------------
    # Session handling
    # ------------------------------------------------------------------
    def _session(self) -> Session:
        if self._session_factory is None:
            raise RuntimeError(
                "PostgresMetadataStore is not configured with a session factory"
            )
        return self._session_factory()

    def _next_index(self) -> int:
        if self._seq is None:
            with self._session() as session:
                max_index = session.execute(
                    select(func.max(ChunkMetadata.chunk_index))
                ).scalar()
            self._seq = (max_index + 1) if max_index is not None else 0
        return self._seq

    # ------------------------------------------------------------------
    # MetadataBackend interface
    # ------------------------------------------------------------------
    def add_documents(
        self,
        texts: list[str],
        filename: str,
        workspace_id: str = DEFAULT_WORKSPACE,
        document_id: Optional[str] = None,
        owner_id: str = "",
    ) -> None:
        document_id = document_id or ""
        start = self._next_index()
        with self._session() as session:
            for offset, text in enumerate(texts):
                session.add(
                    ChunkMetadata(
                        chunk_index=start + offset,
                        document_id=document_id,
                        chunk_id=offset + 1,
                        filename=filename,
                        owner_id=owner_id,
                        workspace_id=workspace_id,
                        text=text,
                    )
                )
            session.commit()
        self._seq = start + len(texts)

    def get_document(self, index: int) -> dict:
        with self._session() as session:
            row = session.execute(
                select(ChunkMetadata).where(ChunkMetadata.chunk_index == index)
            ).first()
        if row is None:
            raise IndexError("document index out of range")
        return self._to_record(row)

    def get_all_documents(
        self,
        owner_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> list[dict]:
        stmt = select(ChunkMetadata).order_by(ChunkMetadata.chunk_index)
        if owner_id is not None:
            stmt = stmt.where(ChunkMetadata.owner_id == owner_id)
        if workspace_id is not None:
            stmt = stmt.where(ChunkMetadata.workspace_id == workspace_id)
        with self._session() as session:
            rows = session.execute(stmt).scalars().all()
        return [self._to_record(row) for row in rows]

    def snapshot_documents(self) -> list[dict]:
        return [dict(record) for record in self.get_all_documents()]

    def restore_documents(self, records: list[dict]) -> None:
        with self._session() as session:
            session.execute(delete(ChunkMetadata))
            for position, record in enumerate(records):
                session.add(
                    ChunkMetadata(
                        chunk_index=position,
                        document_id=record.get("document_id", ""),
                        chunk_id=record.get("chunk_id", position + 1),
                        filename=record.get("filename", ""),
                        owner_id=record.get("owner_id", ""),
                        workspace_id=record.get("workspace_id", ""),
                        text=record.get("text", ""),
                    )
                )
            session.commit()
        self._seq = len(records)

    def persist(self) -> None:
        # Each write is committed immediately, so there is nothing to flush.
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _to_record(row: ChunkMetadata) -> dict:
        return {
            "id": row.chunk_index + 1,
            "workspace_id": row.workspace_id,
            "filename": row.filename,
            "chunk_id": row.chunk_id,
            "document_id": row.document_id,
            "owner_id": row.owner_id,
            "text": row.text,
        }

    @property
    def ntotal(self) -> int:
        if self._seq is not None:
            return self._seq
        with self._session() as session:
            return (
                session.execute(
                    select(func.count()).select_from(ChunkMetadata)
                ).scalar()
                or 0
            )
