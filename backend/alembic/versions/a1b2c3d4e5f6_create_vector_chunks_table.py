"""create vector_chunks table for pgvector backend

Adds the ``vector_chunks`` table used by the optional Postgres/pgvector
``VectorBackend`` implementation. The embedding column is dimension-pinned to
384 to match the default embedding model (``all-MiniLM-L6-v2``); adjust the
dimension here if a different embedding model is configured before running the
migration.

The application keeps using FAISS + JSON until the persistence backend is
switched to ``postgres``; this migration only prepares the schema.

Revision ID: a1b2c3d4e5f6
Revises: c7a9d31e5b42
Create Date: 2026-08-16 20:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from pgvector.sqlalchemy import Vector

# Dimension of the default embedding model (all-MiniLM-L6-v2).
EMBEDDING_DIM = 384


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "c7a9d31e5b42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the vector_chunks table."""
    op.create_table(
        "vector_chunks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
        sa.Column(
            "document_id",
            sa.String(length=64),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "owner_id",
            sa.String(length=64),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "workspace_id",
            sa.String(length=64),
            nullable=False,
            server_default="",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vector_chunks_chunk_index", "vector_chunks", ["chunk_index"])
    op.create_index("ix_vector_chunks_owner_id", "vector_chunks", ["owner_id"])
    op.create_index(
        "ix_vector_chunks_workspace_id", "vector_chunks", ["workspace_id"]
    )


def downgrade() -> None:
    """Drop the vector_chunks table."""
    op.drop_index("ix_vector_chunks_workspace_id", table_name="vector_chunks")
    op.drop_index("ix_vector_chunks_owner_id", table_name="vector_chunks")
    op.drop_index("ix_vector_chunks_chunk_index", table_name="vector_chunks")
    op.drop_table("vector_chunks")
