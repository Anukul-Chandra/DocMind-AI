"""Vector chunk model for the Postgres/pgvector vector backend.

This table backs the ``VectorBackend`` implementation used by the (optional)
Postgres persistence backend. It stores one row per indexed chunk embedding and
preserves the positional ``chunk_index`` that mirrors the order of the
companion metadata records, exactly like the FAISS index positions in the
JSON-backed implementation.

Owner/workspace/document identifiers are stored alongside the embedding so a
future coordinated write (or a DB-level ownership filter) can use them; the
current ``VectorBackend.add_embeddings`` contract does not carry that metadata,
so those columns default to empty until populated by the metadata path.
"""

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from pgvector.sqlalchemy import Vector


class VectorChunk(Base):
    """A single indexed chunk embedding."""

    __tablename__ = "vector_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chunk_index: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True
    )
    embedding = mapped_column(Vector())
    document_id: Mapped[str] = mapped_column(
        String(64), default="", server_default="", index=True
    )
    owner_id: Mapped[str] = mapped_column(
        String(64), default="", server_default="", index=True
    )
    workspace_id: Mapped[str] = mapped_column(
        String(64), default="", server_default="", index=True
    )
