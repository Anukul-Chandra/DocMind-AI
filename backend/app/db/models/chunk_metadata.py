"""Chunk metadata model for the Postgres/pgvector metadata backend.

This table backs the ``MetadataBackend`` implementation used by the (optional)
Postgres persistence backend. Each row is one chunk and preserves the exact
fields the application reads from the JSON ``MetadataStore`` records:

    id, workspace_id, filename, chunk_id, document_id, owner_id, text

A gapless, 0-based ``chunk_index`` mirrors the order of the companion vector
rows (``vector_chunks.chunk_index``), exactly like the positional alignment
between the FAISS index and the JSON metadata list. The JSON ``id`` field is
derived as ``chunk_index + 1`` to stay compatible with the existing records,
so a future JSON -> Postgres migration needs no upper-layer changes.
"""

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChunkMetadata(Base):
    """A single indexed chunk's metadata."""

    __tablename__ = "chunk_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chunk_index: Mapped[int] = mapped_column(
        Integer, nullable=False, unique=True, index=True
    )
    document_id: Mapped[str] = mapped_column(
        String(64), default="", server_default="", index=True
    )
    chunk_id: Mapped[int] = mapped_column(Integer, default=1)
    filename: Mapped[str] = mapped_column(String(512), default="")
    owner_id: Mapped[str] = mapped_column(
        String(64), default="", server_default="", index=True
    )
    workspace_id: Mapped[str] = mapped_column(
        String(64), default="", server_default="", index=True
    )
    text: Mapped[str] = mapped_column(Text, default="")
